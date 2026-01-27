import os
import joblib
import pandas as pd
import numpy as np
import shap
import xgboost as xgb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from databases import Database
from dotenv import load_dotenv
import ssl

# 1. SETUP & CONFIGURATION
load_dotenv()
# Update this with your actual PostgreSQL credentials
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:3312@localhost:5432/postgres")	

#DATABASE CONNECTION (The SSL Fix)
app = FastAPI(title="Transparent Lender: Real-Time Credit Portal")
if "localhost" not in DATABASE_URL:
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

# --- MODEL LOADING ---
model = xgb.XGBClassifier()
explainer = None

try:
    model.load_model("credit_risk_model.json")
    print("Model loaded via JSON successfully.")

    model_features = [
        'external_risk_estimate_c', 'net_fraction_revolving_burden', 
        'num_inq_last_6m', 'percent_trades_never_delq', 'm_since_recent_delq'
    ]


    model.feature_names_in_ = model_features

    background_data = pd.DataFrame(np.zeros((10, 5)), columns=model_features)
    explainer = shap.KernelExplainer(model.predict_proba, background_data)
    print("SHAP Explainer initialized.")

except Exception as e:
    print(f"CRITICAL MODEL ERROR: {e}")

@app.on_event("startup")
async def startup():
   try:
       await database.connect()
       # Ping the DB to verify connection for DevOps logs
       await database.execute("SELECT 1")
       print("DATABASE: Connected and verified.")
   except Exception as e:
       print(f"DATABASE: Connection failed: {e}")


@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()



# --- SEARCH ENDPOINT ---
@app.get("/application/{app_id}")
async def get_application(app_id: int):
    try:
       # 1. Fetch data from PostgreSQL
       query = "SELECT * FROM application_master_record WHERE applicant_id = :app_id"
       row = await database.fetch_one(query=query, values={"app_id": app_id})
    
       if not row:
           raise HTTPException(status_code=404, detail="Applicant not found")
    
       # 2. Convert to dictionary and prepare features for the model
       data = dict(row)
    
        # We must extract only the 5 features your model was trained on
       input_features = ['external_risk_estimate_c', 'net_fraction_revolving_burden', 
                      'num_inq_last_6m', 'percent_trades_never_delq', 'm_since_recent_delq']
    
        # Create a DataFrame for the model (matching your training format)
       input_df = pd.DataFrame([data])[input_features]

       # 3. Live Prediction
       prediction = int(model.predict(input_df)[0])
       probability = float(model.predict_proba(input_df)[0][1])

       # 4. Live SHAP Explanation (The 'Why')
       # Using the KernelExplainer you defined in your snippet
       shap_values = explainer.shap_values(input_df)
    

        # Handle the list returned by KernelExplainer
       active_shap = shap_values[1] if isinstance(shap_values, list) else shap_values

       # Identify the top feature (Primary Factor)
       # np.abs(shap_values).argmax(axis=1) finds the index of the most influential feature
       top_reason_idx = np.abs(shap_values).argmax(axis=1)[0]
       primary_factor = input_features[top_reason_idx]

       # 5. Bundle everything for Lovable
       data["prediction"] = prediction
       data["probability"] = round(probability * 100, 2)
       data["primary_factor"] = primary_factor
    
       return data
    except Exception as e:
       print(f"API ERROR: {e}")
       raise HTTPException(status_code=500, detail=str(e))
 
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