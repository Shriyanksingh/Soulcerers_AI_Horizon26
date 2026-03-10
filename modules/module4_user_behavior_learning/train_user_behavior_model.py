from pathlib import Path

import numpy as np
import pandas as pd
from joblib import dump
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent
MODULE4_DATA_DIR = PROJECT_ROOT / "data" / "module4"
MODULE4_MODELS_DIR = PROJECT_ROOT / "models" / "module4"


def resolve_dataset_path() -> Path:
    """Locate the user behavior dataset."""
    candidates = [
        MODULE4_DATA_DIR / "user_behavior_dataset.csv",
        PROJECT_ROOT / "user_behavior_dataset.csv",
        PROJECT_ROOT / "archive (1)" / "user_behavior_dataset.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError(
        "user_behavior_dataset.csv not found. Generate it before training."
    )


def main() -> None:
    # 1) Load synthetic behavior dataset
    dataset_path = resolve_dataset_path()
    df = pd.read_csv(dataset_path)
    df["user_id"] = df["user_id"].astype(str).str.strip().str.lower()
    df["day_of_week"] = df["day_of_week"].astype(str).str.strip().str.title()
    df["weather_main"] = df["weather_main"].astype(str).str.strip().str.title()
    df["destination"] = df["destination"].astype(str).str.strip().str.title()
    df["traffic_level"] = df["traffic_level"].astype(str).str.strip().str.title()

    # 2) Define features and target
    feature_columns = [
        "user_id",
        "day_of_week",
        "weather_main",
        "destination",
        "hour",
        "traffic_level",
    ]
    target_column = "usual_departure_hour"

    X = df[feature_columns].copy()
    y = df[target_column].copy()

    # 3) Build preprocessing pipeline
    categorical_features = [
        "user_id",
        "day_of_week",
        "weather_main",
        "destination",
        "traffic_level",
    ]
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

    # 4) Regressor model for hour prediction
    model = Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            (
                "regressor",
                RandomForestRegressor(
                    n_estimators=180,
                    max_depth=16,
                    min_samples_leaf=2,
                    random_state=42,
                    n_jobs=1,  # stable in restricted Windows environments
                ),
            ),
        ]
    )

    # 5) Split, train, evaluate
    X_train, X_test, y_train, y_test = train_test_split(
        X,
        y,
        test_size=0.2,
        random_state=42,
    )

    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)

    mae = mean_absolute_error(y_test, y_pred)
    r2 = r2_score(y_test, y_pred)
    print(f"Test MAE (hours): {mae:.3f}")
    print(f"Test R2: {r2:.4f}")

    y_pred_hour = np.clip(np.rint(y_pred), 0, 23).astype(int)
    rounded_hour_accuracy = (y_pred_hour == y_test.astype(int).to_numpy()).mean()
    print(f"Rounded Hour Accuracy: {rounded_hour_accuracy:.4f}")

    # 6) Save full pipeline
    output_path = MODULE4_MODELS_DIR / "user_behavior_model.pkl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    dump(model, output_path)
    print(f"Saved trained model to: {output_path}")


if __name__ == "__main__":
    main()
