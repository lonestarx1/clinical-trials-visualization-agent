from enum import StrEnum


class ChartType(StrEnum):
    BAR_CHART = "bar_chart"
    GROUPED_BAR_CHART = "grouped_bar_chart"
    TIME_SERIES = "time_series"
    HISTOGRAM = "histogram"
    SCATTER_PLOT = "scatter_plot"
    NETWORK_GRAPH = "network_graph"
    METRIC = "metric"


class Intent(StrEnum):
    TREND = "trend"
    DISTRIBUTION = "distribution"
    TOP_N = "top_n"
    COMPARISON = "comparison"
    GEOGRAPHIC = "geographic"
    NETWORK = "network"
    NUMERIC_DISTRIBUTION = "numeric_distribution"
    NUMERIC_RELATIONSHIP = "numeric_relationship"
    SINGLE_NUMBER = "single_number"
