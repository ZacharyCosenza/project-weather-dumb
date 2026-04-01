from kedro.pipeline import Pipeline, node, pipeline

from .nodes import plot_eda, train_and_evaluate


def create_pipeline(**kwargs) -> Pipeline:
    return pipeline([
        node(
            func=plot_eda,
            inputs={
                "hourly_features": "hourly_features",
                "feature_cols":    "params:feature_cols",
            },
            outputs=["plot_distributions", "plot_correlations"],
            name="plot_eda",
        ),
        node(
            func=train_and_evaluate,
            inputs={
                "hourly_features": "hourly_features",
                "feature_cols":    "params:feature_cols",
                "xgb":             "params:xgb",
                "test_size":       "params:test_size",
                "val_split":       "params:val_split",
            },
            outputs=["model_precip", "model_temp", "metrics", "shap_precip", "shap_temp"],
            name="train_and_evaluate",
        ),
    ])
