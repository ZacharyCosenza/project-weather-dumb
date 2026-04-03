from kedro.pipeline import Pipeline, node, pipeline

from .nodes import run_inference, run_qc


def create_pipeline(**kwargs) -> Pipeline:
    return pipeline([
        node(
            func=run_inference,
            inputs={
                "hourly_features":       "hourly_features",
                "model_precip":          "model_precip",
                "model_temp":            "model_temp",
                "feature_cols":          "params:feature_cols",
                "confidence_thresholds": "params:confidence_thresholds",
            },
            outputs="predictions_raw",
            name="run_inference",
        ),
        node(
            func=run_qc,
            inputs={
                "predictions": "predictions_raw",
                "feature_cols": "params:feature_cols",
            },
            outputs="predictions",
            name="run_qc",
        ),
    ])
