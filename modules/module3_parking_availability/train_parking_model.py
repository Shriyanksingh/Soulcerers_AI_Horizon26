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
MODULE3_DATA_DIR = PROJECT_ROOT / "data" / "module3"
MODULE3_MODELS_DIR = PROJECT_ROOT / "models" / "module3"


def resolve_dataset_path() -> Path:
    """Find the parking dataset in expected local locations."""
    candidates = [
        MODULE3_DATA_DIR / "parking_dataset.csv",
        PROJECT_ROOT / "parking_dataset.csv",
        PROJECT_ROOT / "archive (1)" / "parking_dataset.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "parking_dataset.csv not found. Please generate the synthetic dataset first."
    )


def main() -> None:
    # 1) Load dataset
    dataset_path = resolve_dataset_path()
    df = pd.read_csv(dataset_path)
    df["area_type"] = df["area_type"].astype(str).str.strip().str.lower()
    df["day_of_week"] = df["day_of_week"].astype(str).str.strip().str.title()
    df["holiday"] = df["holiday"].astype(str).str.strip().str.title()
    df["traffic_level"] = df["traffic_level"].astype(str).str.strip().str.title()
    df["parking_availability"] = (
        df["parking_availability"].astype(str).str.strip().str.title()
    )

    # 2) Define feature columns and target
    feature_columns = ["area_type", "hour", "day_of_week", "holiday", "traffic_level"]
    target_column = "parking_availability"

    X = df[feature_columns].copy()
    y = df[target_column].copy()

    # 3) Preprocess categorical features with one-hot encoding
    categorical_features = ["area_type", "day_of_week", "holiday", "traffic_level"]
    numeric_features = ["hour"]

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

    # 4) Build model pipeline: preprocessing + classifier
    model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "classifier",
                RandomForestClassifier(
                    n_estimators=180,
                    max_depth=14,
                    min_samples_leaf=2,
                    random_state=42,
                    n_jobs=1,  # stable in restricted Windows environments
                ),
            ),
        ]
    )

    # 5) Split data for evaluation
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
        stratify=y,
    )

    # 6) Train model
    model.fit(X_train, y_train)

    # 7) Evaluate model
    y_pred = model.predict(X_test)
    accuracy = accuracy_score(y_test, y_pred)

    print(f"Test Accuracy: {accuracy:.4f}")
    print("\nClassification Report:")
    print(classification_report(y_test, y_pred))

    labels = sorted(y.unique())
    cm = confusion_matrix(y_test, y_pred, labels=labels)
    cm_df = pd.DataFrame(cm, index=labels, columns=labels)
    print("\nConfusion Matrix:")
    print(cm_df)

    # 8) Save trained pipeline (includes preprocessing)
    output_model_path = MODULE3_MODELS_DIR / "parking_model.pkl"
    output_model_path.parent.mkdir(parents=True, exist_ok=True)
    dump(model, output_model_path)
    print(f"\nSaved trained model to: {output_model_path}")


if __name__ == "__main__":
    main()
