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
            outputs=["plot_distributions", "plot_correlations", "plot_targets", "plot_features_time"],
            name="plot_eda",
        ),
        node(
            func=train_and_evaluate,
            inputs={
                "hourly_features":  "hourly_features",
                "feature_cols":     "params:feature_cols",
                "xgb":              "params:xgb",
                "train_end":        "params:train_end",
                "val_end":          "params:val_end",
                "random_test_frac":        "params:random_test_frac",
                "train_subsample_frac":    "params:train_subsample_frac",
            },
            outputs=["model_temp", "plot_metrics", "shap_temp", "plot_pdp"],
            name="train_and_evaluate",
        ),
    ])
