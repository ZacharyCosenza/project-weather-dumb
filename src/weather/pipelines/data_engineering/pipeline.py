from kedro.pipeline import Pipeline, node, pipeline

from .nodes import fetch_raw, merge_features


def create_pipeline(**kwargs) -> Pipeline:
    return pipeline([
        node(
            func=fetch_raw,
            inputs={
                "start_date": "params:start_date",
                "end_date":   "params:end_date",
                "nyc_lat":    "params:nyc_lat",
                "nyc_lon":    "params:nyc_lon",
                "cold_c":     "params:cold_c",
                "hot_c":      "params:hot_c",
            },
            outputs=["raw_openmeteo", "raw_nyiso", "raw_mta", "raw_311", "raw_crashes"],
            name="fetch_raw",
        ),
        node(
            func=merge_features,
            inputs={
                "raw_openmeteo": "raw_openmeteo",
                "raw_nyiso":     "raw_nyiso",
                "raw_mta":       "raw_mta",
                "raw_311":       "raw_311",
                "raw_crashes":   "raw_crashes",
                "mta_lag":       "params:mta_lag",
                "lag_311":       "params:lag_311",
                "crashes_lag":   "params:crashes_lag",
                "lag_window":    "params:lag_window",
            },
            outputs="hourly_features",
            name="merge_features",
        ),
    ])
