from kedro.pipeline import Pipeline, node, pipeline

from .nodes import run_inference


def create_pipeline(**kwargs) -> Pipeline:
    return pipeline([
        node(
            func=run_inference,
            inputs={
                "hourly_features": "hourly_features",
                "model_temp":      "model_temp",
                "feature_cols":    "params:feature_cols",
            },
            outputs="predictions",
            name="run_inference",
        )
    ])
