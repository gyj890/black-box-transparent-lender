import os
import joblib
import pandas as pd
import numpy as np
import shap
import json
import xgboost as xgb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from databases import Database
from dotenv import load_dotenv
import ssl

# 1. SETUP & CONFIGURATION
load_dotenv()

# Change this logic to handle missing secrets gracefully
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # This prevents the KeyError by not initializing the DB with an empty string
    print("❌ ERROR: DATABASE_URL is not set. Check Hugging Face Secrets.")
    # You can set a dummy string here just to let the app start (though DB features won't work)
    DATABASE_URL = "postgresql://placeholder:placeholder@localhost:5432/placeholder"

app = FastAPI(title="Transparent Lender: Real-Time Credit Portal")

# Use a cleaner check for SSL
if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
    database = Database(DATABASE_URL, ssl=True)
else:
    database = Database(DATABASE_URL)

	
@app.get("/")
def health_check():
    return {"status": "alive", "message": "Lender API is running"}

# Add Middleware ONCE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODEL LOADING (The Joblib Way) ---
model = None
explainer = None

# We keep this list because the API endpoints need it to filter columns
model_features = [
    'external_risk_estimate_c', 'net_fraction_revolving_burden', 
    'num_inq_last_6m', 'percent_trades_never_delq', 'm_since_recent_delq'
]

try:
    # Joblib restores the FULL object, including metadata patched locally
    model = joblib.load("credit_model_v2.joblib")
    print("MODEL: Loaded via Joblib successfully.")

    # Get the booster and force-fix the base_score in RAM
    booster = model.get_booster()
    # This overwrites the '[5.22...]' with a clean numeric string '0.522...'
    booster.set_attr(base_score="0.52240944", _estimator_type='classifier')
    model._estimator_type = "classifier"

    
    # TreeExplainer works perfectly with Joblib-loaded models
    explainer = shap.TreeExplainer(model)
    
    if explainer.expected_value is None:
        raise ValueError("SHAP expected_value is empty")
        
    print("✅ SUCCESS: SHAP Explainer initialized and brackets bypassed!")

except Exception as e:
    print(f"CRITICAL LOADING ERROR: {e}")
    explainer = None

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()


# ... (Keep startup/shutdown blocks as they are) ...

# --- SEARCH ENDPOINT ---
@app.get("/application/{app_id}")
async def get_application(app_id: int):
    try:
        query = "SELECT * FROM application_master_record WHERE applicant_id = :app_id"
        row = await database.fetch_one(query=query, values={"app_id": app_id})
        
        if not row:
            raise HTTPException(status_code=404, detail="Applicant not found")
        
        raw_data = dict(row)
        data = {k.lower(): v for k, v in raw_data.items()}
        print(f"DEBUG: Keys received from Neon: {list(data.keys())}")
        
        input_features = ['external_risk_estimate_c', 'net_fraction_revolving_burden', 
                          'num_inq_last_6m', 'percent_trades_never_delq', 'm_since_recent_delq']
        
        for f in input_features:
            if f not in data:
                data[f] = 0
        
        input_df = pd.DataFrame([data])[input_features]

        # Prediction logic
        prediction = int(model.predict(input_df)[0])
        probability = float(model.predict_proba(input_df)[0][1])
        
        # SHAP Explanation logic
        shap_values = explainer.shap_values(input_df)
        active_shap = shap_values[1] if isinstance(shap_values, list) else shap_values
        
        top_reason_idx = np.abs(active_shap).argmax(axis=1)[0]
        primary_factor = input_features[top_reason_idx].replace('_', ' ').title()

        data["prediction"] = prediction
        data["probability"] = round(probability * 100, 2)
        data["primary_factor"] = primary_factor
        
        return data
    except Exception as e:
        print(f"API ERROR: {e}")
        raise HTTPException(status_code=500, detail=str(e))


#----Predict Endpoint------

@app.post("/predict")
async def predict_risk(data: dict):
    try:
        # 1. SANITIZE KEYS (Fixes mapping issues between JS and Python)
        # This converts all keys to lowercase to match model_features
        clean_data = {k.lower(): v for k, v in data.items()}
        input_df = pd.DataFrame([clean_data])
        
        # 2. FEATURE SELECTION (Must match your .pkl model training)
        model_features = [
            'external_risk_estimate_c', 
            'net_fraction_revolving_burden', 
            'num_inq_last_6m', 
            'percent_trades_never_delq', 
            'm_since_recent_delq'
        ]
        
        # Ensure all columns exist; if missing, set to 0
        for col in model_features:
            if col not in input_df.columns:
                input_df[col] = 0
        
        # 3. TYPE CONVERSION
        # Convert to numeric and select only the 5 features needed
        features_only = input_df[model_features].apply(pd.to_numeric, errors='coerce').fillna(0)
        
        # 4. RUN MODEL
        prediction = model.predict(features_only)[0]
        # Get risk probability (Class 1 = Bad/Rejected)
        probability_array = model.predict_proba(features_only)
        probability = probability_array[0][1] 
        
        # 5. DYNAMIC FACTOR ANALYSIS (Enhanced)
        burden = float(clean_data.get("net_fraction_revolving_burden", 0))
        score = float(clean_data.get("external_risk_estimate_c", 0))
        inquiries = float(clean_data.get("num_inq_last_6m", 0))
        on_time = float(clean_data.get("percent_trades_never_delq", 0))
        months_since_delq = float(clean_data.get("m_since_recent_delq", 0))
        
        # Logic to find the primary driver of the result
        if prediction == 1:  # If Rejected
            if burden > 50:
                factor = "excessive revolving burden (high credit card usage)"
            elif score < 65:
                factor = "low credit trust score from external bureaus"
            elif inquiries > 3:
                factor = "too many recent credit inquiries"
            elif on_time < 90:
                factor = "inconsistent on-time payment history"
            elif months_since_delq < 12 and months_since_delq != 0:
                factor = "recent delinquency recorded within the last year"
            else:
                factor = "high overall risk profile based on historical data"
        else:  # If Approved
            factor = "strong credit trust score and healthy payment behavior"
        
        return {
            "prediction": int(prediction), 
            "probability": round(float(probability) * 100, 2),
            "primary_factor": factor 
        }

    except Exception as e:
        print(f"ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Serve the static folder (CSS, JS, images)
# Hugging Face needs this folder to exist in your repository
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# Serve the main dashboard HTML
@app.get("/")
async def read_index():
    return FileResponse('static/index.html')