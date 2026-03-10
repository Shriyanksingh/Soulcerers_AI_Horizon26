from pathlib import Path

import pandas as pd
from joblib import dump
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
MODULE1_DATA_DIR = PROJECT_ROOT / "data" / "module1"
MODULE1_MODELS_DIR = PROJECT_ROOT / "models" / "module1"


def resolve_processed_dataset() -> Path:
    """Locate the processed dataset in expected locations."""
    candidates = [
        MODULE1_DATA_DIR / "processed" / "traffic_dataset_processed.csv",
        PROJECT_ROOT / "traffic_dataset_processed.csv",
        PROJECT_ROOT / "archive (1)" / "traffic_dataset_processed.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "traffic_dataset_processed.csv not found. Run prepare_dataset.py first."
    )


def main() -> None:
    # Load processed dataset
    input_path = resolve_processed_dataset()
    df = pd.read_csv(input_path)

    # Define features and target
    target_column = "traffic_level"
    feature_columns = [
        "hour",
        "day_of_week",
        "weather_main",
        "temp",
        "rain_1h",
        "holiday",
    ]

    X = df[feature_columns].copy()
    y = df[target_column].copy()

    # Separate numeric and categorical columns for preprocessing
    categorical_features = ["weather_main", "holiday"]
    numeric_features = ["hour", "day_of_week", "temp", "rain_1h"]

    # One-hot encode categorical features and pass numeric features through as-is
    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                OneHotEncoder(handle_unknown="ignore"),
                categorical_features,
            ),
            ("numeric", "passthrough", numeric_features),
        ]
    )

    # Build a pipeline: preprocessing + Random Forest classifier
    model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=200,
                    random_state=42,
                    n_jobs=1,
                ),
            ),
        ]
    )

    # Split data for training and evaluation
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    # Train the model
    model.fit(X_train, y_train)

    # Evaluate performance on holdout test set
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"Test Accuracy: {accuracy:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    # Print confusion matrix with class labels for readability
    labels = sorted(y.unique())
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=labels, columns=labels)
    print("\nConfusion Matrix:")
    print(cm_df)

    # Save the trained pipeline (preprocessing + model) for later inference
    output_model_path = MODULE1_MODELS_DIR / "traffic_model.pkl"
    output_model_path.parent.mkdir(parents=True, exist_ok=True)
    dump(model, output_model_path)
    print(f"\nSaved trained model to: {output_model_path}")


if __name__ == "__main__":
    main()
