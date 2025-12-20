# Black Box: The Transparent Lender
### Solving the Black Box Problem in Credit Risk with Explainable AI (XAI)

## The Motivation
In the financial industry, high-accuracy machine learning models are often black boxes, meaning we can see the prediction, but we can't explain the reasoning behind it. This is a massive problem for transparency and regulatory compliance.

I built **The Transparent Lender** to bridge this gap. This project demonstrates how to use a high-performance **XGBoost** model while maintaining full accountability through **SHAP (SHapley Additive exPlanations)**. It’s designed to provide the specific "Reason Codes" required by laws like the **Equal Credit Opportunity Act (ECOA)**.

---

## How the Pipeline Works
Instead of just handing off data to a model, I’ve structured this as a professional analytical pipeline:

* **Data Strategy**: I used **PostgreSQL** for reliable data storage, ensuring that every loan record is structured and queryable for feature engineering.
* **Modeling Engine**: The core uses **Python** and **XGBoost**. While these models are complex, they are industry favorites for their predictive power.
* **The Transparency Layer**: This is the most critical part. By applying **SHAP**, I translate "weights and biases" into human-readable feature importance. It allows us to tell a customer exactly why their application was approved or denied based on their specific data points.

---

## Project Structure
A project is only as good as its organization. I’ve followed a standard production hierarchy:

* **data/**: Raw and processed credit datasets
* **notebooks/**: Step-by-step EDA and XAI prototyping
* **sql/**: Database scripts for data extraction
* **src/**: Refined Python scripts for the model pipeline
* **docs/**: Technical notes and regulatory references
