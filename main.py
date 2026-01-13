import os
import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from databases import Database
from dotenv import load_dotenv

# 1. SETUP & CONFIGURATION
load_dotenv()
# Update this with your actual PostgreSQL credentials
DATABASE_URL = "postgresql://postgres:3312@localhost:5432/postgres"

app = FastAPI(title="Transparent Lender: Real-Time Credit Portal")
database = os.getenv(DATABASE_URL)

# Add Middleware ONCE
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- MODEL LOADING ---
try:
    model = joblib.load("credit_risk_model.pkl")
    print("Model loaded successfully.")
except Exception as e:
    print(f"Error loading model: {e}")

@app.on_event("startup")
async def startup():
    await database.connect()

@app.on_event("shutdown")
async def shutdown():
    await database.disconnect()

# --- SEARCH ENDPOINT ---
@app.get("/application/{app_id}")
async def get_application(app_id: int):
    # Ensure table and column names match your PostgreSQL exactly
    query = "SELECT * FROM application_master_record WHERE applicant_id = :app_id"
    result = await database.fetch_one(query=query, values={"app_id": app_id})
    if not result:
        raise HTTPException(status_code=404, detail="Applicant ID not found")
    
    # We return the dict so JS can map it to form fields
    return dict(result)

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
        
        # 5. DYNAMIC FACTOR ANALYSIS
        # Use .get() on the clean dictionary to avoid KeyErrors
        burden = float(clean_data.get("net_fraction_revolving_burden", 0))
        score = float(clean_data.get("external_risk_estimate_c", 0))
        
        if burden > 50:
            factor = "excessive revolving burden"
        elif score < 70:
            factor = "low credit bureau risk score"
        else:
            factor = "standard risk profile"
        
        return {
            "prediction": int(prediction), 
            "probability": round(float(probability) * 100, 2),
            "primary_factor": factor 
        }
    except Exception as e:
        print(f"CRITICAL ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Backend Error: {str(e)}")