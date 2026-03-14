"""
Tests for mom_gen.py - CIO Momentum Dashboard Generator
"""

import os
import sys
import tempfile
import types

import numpy as np
import pandas as pd
import pytest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Mock yfinance before importing mom_gen since it may not be installed
if "yfinance" not in sys.modules:
    yf_mock = types.ModuleType("yfinance")
    yf_mock.download = lambda *a, **kw: pd.DataFrame()
    sys.modules["yfinance"] = yf_mock

from mom_gen import (
    clean_symbol,
    load_etf_universe,
    fetch_data,
    calculate_metrics,
    calculate_correlations,
    generate_html,
)


# ======================== FIXTURES ========================


@pytest.fixture
def sample_csv(tmp_path):
    """Create a sample mapping.csv for testing."""
    csv_content = (
        "Name,Symbol,Region,Category,Subcategory,High Vol\n"
        "SPDR S&P 500,SPY,US,ETF,US Broad Market,FALSE\n"
        "Invesco QQQ Trust,QQQ.O,US,ETF,US Tech,FALSE\n"
        "SPDR Gold Shares,GLD,Commodities,ETF,Precious Metals,FALSE\n"
        "iShares MSCI India ETF,INDA,Emerging Markets,ETF,ETF,TRUE\n"
        "Hang Seng H-Share,2828.HK,Emerging Markets,ETF,ETF,FALSE\n"
    )
    csv_file = tmp_path / "mapping.csv"
    csv_file.write_text(csv_content)
    return str(csv_file)


@pytest.fixture
def sample_csv_with_duplicates(tmp_path):
    """CSV with duplicate symbols."""
    csv_content = (
        "Name,Symbol,Region,Category,Subcategory,High Vol\n"
        "SPDR S&P 500,SPY,US,ETF,US Broad Market,FALSE\n"
        "SPDR S&P 500 Duplicate,SPY,US,ETF,US Large Cap,TRUE\n"
        "Invesco QQQ Trust,QQQ.O,US,ETF,US Tech,FALSE\n"
    )
    csv_file = tmp_path / "mapping_dup.csv"
    csv_file.write_text(csv_content)
    return str(csv_file)


@pytest.fixture
def sample_csv_missing_columns(tmp_path):
    """CSV missing required columns."""
    csv_content = (
        "Name,Symbol,Region\n"
        "SPDR S&P 500,SPY,US\n"
    )
    csv_file = tmp_path / "mapping_bad.csv"
    csv_file.write_text(csv_content)
    return str(csv_file)


@pytest.fixture
def sample_prices():
    """Generate realistic price data for testing (300 trading days)."""
    np.random.seed(42)
    dates = pd.bdate_range(start="2024-01-01", periods=300)
    # Simulate an uptrending stock with daily ~0.05% return + noise
    daily_returns = np.random.normal(0.0005, 0.015, 300)
    prices = 100 * np.cumprod(1 + daily_returns)
    return pd.Series(prices, index=dates, name="SPY")


@pytest.fixture
def sample_prices_short():
    """Price data with fewer than 252 days (insufficient)."""
    np.random.seed(42)
    dates = pd.bdate_range(start="2024-01-01", periods=100)
    prices = 100 + np.cumsum(np.random.normal(0, 1, 100))
    return pd.Series(prices, index=dates, name="SHORT")


@pytest.fixture
def multi_ticker_prices():
    """Generate price data for multiple tickers."""
    np.random.seed(42)
    dates = pd.bdate_range(start="2024-01-01", periods=300)
    data = {}
    # Correlated tickers
    base_returns = np.random.normal(0.0005, 0.015, 300)
    data["SPY"] = 100 * np.cumprod(1 + base_returns)
    # Correlated with SPY
    data["QQQ"] = 200 * np.cumprod(1 + base_returns * 1.2 + np.random.normal(0, 0.005, 300))
    # Uncorrelated
    data["GLD"] = 150 * np.cumprod(1 + np.random.normal(0.0002, 0.01, 300))
    return pd.DataFrame(data, index=dates)


@pytest.fixture
def sample_maps():
    """Sample mapping dictionaries."""
    return {
        "sector_map": {"SPY": "US Broad Market", "QQQ": "US Tech", "GLD": "Precious Metals"},
        "country_map": {"SPY": "US", "QQQ": "US", "GLD": "Commodities"},
        "name_map": {"SPY": "SPDR S&P 500", "QQQ": "Invesco QQQ", "GLD": "SPDR Gold"},
        "category_map": {"SPY": "ETF", "QQQ": "ETF", "GLD": "ETF"},
    }


# ======================== TESTS: clean_symbol ========================


class TestCleanSymbol:
    """Tests for the clean_symbol function."""

    def test_plain_symbol_unchanged(self):
        assert clean_symbol("SPY") == "SPY"

    def test_nasdaq_suffix_removed(self):
        assert clean_symbol("QQQ.O") == "QQQ"

    def test_nyse_arca_suffix_removed(self):
        assert clean_symbol("COPX.K") == "COPX"

    def test_hong_kong_suffix_kept(self):
        assert clean_symbol("2828.HK") == "2828.HK"

    def test_toronto_suffix_kept(self):
        assert clean_symbol("XIU.TO") == "XIU.TO"

    def test_milan_suffix_kept(self):
        assert clean_symbol("ENI.MI") == "ENI.MI"

    def test_warsaw_suffix_kept(self):
        assert clean_symbol("CDR.WA") == "CDR.WA"

    def test_nse_india_suffix_kept(self):
        assert clean_symbol("RELIANCE.NS") == "RELIANCE.NS"

    def test_bse_india_suffix_kept(self):
        assert clean_symbol("RELIANCE.BO") == "RELIANCE.BO"

    def test_vietnam_hm_suffix_removed(self):
        assert clean_symbol("VNM.HM") == "VNM"

    def test_vietnam_hno_suffix_removed(self):
        assert clean_symbol("VNM.HNO") == "VNM"

    def test_nan_returns_none(self):
        assert clean_symbol(float("nan")) is None

    def test_none_via_pandas_na(self):
        assert clean_symbol(pd.NA) is None

    def test_whitespace_stripped(self):
        assert clean_symbol("  SPY  ") == "SPY"

    def test_numeric_symbol_as_string(self):
        assert clean_symbol(2828) == "2828"

    def test_symbol_with_unknown_suffix(self):
        """Unknown suffixes should be left as-is."""
        assert clean_symbol("ABC.XY") == "ABC.XY"


# ======================== TESTS: load_etf_universe ========================


class TestLoadEtfUniverse:
    """Tests for loading the ETF universe from CSV."""

    def test_load_valid_csv(self, sample_csv):
        tickers, sector_map, country_map, name_map, highvol_map, category_map, regions_map = load_etf_universe(sample_csv)
        assert len(tickers) == 5
        assert "SPY" in tickers
        assert "QQQ" in tickers  # QQQ.O cleaned to QQQ
        assert "2828.HK" in tickers

    def test_sector_map_populated(self, sample_csv):
        tickers, sector_map, *_ = load_etf_universe(sample_csv)
        assert sector_map["SPY"] == "US Broad Market"
        assert sector_map["QQQ"] == "US Tech"
        assert sector_map["GLD"] == "Precious Metals"

    def test_country_map_populated(self, sample_csv):
        _, _, country_map, *_ = load_etf_universe(sample_csv)
        assert country_map["SPY"] == "US"
        assert country_map["GLD"] == "Commodities"

    def test_name_map_populated(self, sample_csv):
        _, _, _, name_map, *_ = load_etf_universe(sample_csv)
        assert name_map["SPY"] == "SPDR S&P 500"
        assert name_map["QQQ"] == "Invesco QQQ Trust"

    def test_highvol_map(self, sample_csv):
        _, _, _, _, highvol_map, *_ = load_etf_universe(sample_csv)
        assert highvol_map["SPY"] is False
        assert highvol_map["INDA"] is True

    def test_category_map(self, sample_csv):
        _, _, _, _, _, category_map, _ = load_etf_universe(sample_csv)
        assert category_map["SPY"] == "ETF"

    def test_duplicates_removed(self, sample_csv_with_duplicates):
        tickers, sector_map, *_ = load_etf_universe(sample_csv_with_duplicates)
        spy_count = tickers.count("SPY")
        assert spy_count == 1
        # First occurrence kept
        assert sector_map["SPY"] == "US Broad Market"

    def test_missing_columns_raises(self, sample_csv_missing_columns):
        with pytest.raises(ValueError, match="CSV missing required columns"):
            load_etf_universe(sample_csv_missing_columns)

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_etf_universe("/nonexistent/path/mapping.csv")

    def test_symbols_cleaned(self, sample_csv):
        tickers, *_ = load_etf_universe(sample_csv)
        # QQQ.O should be cleaned to QQQ
        assert "QQQ" in tickers
        assert "QQQ.O" not in tickers


# ======================== TESTS: calculate_metrics ========================


class TestCalculateMetrics:
    """Tests for the core metrics calculation function."""

    def test_returns_dict_with_expected_keys(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices,
            "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
            sample_maps["name_map"],
            sample_maps["category_map"],
        )
        assert result is not None
        expected_keys = {
            "ticker", "name", "sector", "country", "regions", "category", "isETF",
            "price", "return6m", "sortino", "weeksDown", "zScore",
            "slope", "aboveMA30", "aboveMA60", "aboveMA200", "maxDD",
        }
        assert set(result.keys()) == expected_keys

    def test_ticker_and_metadata(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
            sample_maps["name_map"],
            sample_maps["category_map"],
        )
        assert result["ticker"] == "SPY"
        assert result["name"] == "SPDR S&P 500"
        assert result["sector"] == "US Broad Market"
        assert result["country"] == "US"
        assert result["category"] == "ETF"
        assert result["isETF"] is True

    def test_insufficient_data_returns_none(self, sample_prices_short, sample_maps):
        result = calculate_metrics(
            sample_prices_short, "SHORT",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        assert result is None

    def test_return_6m_is_percentage(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        # 6-month return should be a reasonable percentage (not 0 or extreme)
        assert isinstance(result["return6m"], float)
        assert -100 < result["return6m"] < 500

    def test_sortino_ratio_type(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        assert isinstance(result["sortino"], float)

    def test_weeks_down_range(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        assert 0 <= result["weeksDown"] <= 12

    def test_z_score_is_float(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        assert isinstance(result["zScore"], float)

    def test_slope_is_float(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        assert isinstance(result["slope"], float)

    def test_moving_averages_are_booleans(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        assert isinstance(result["aboveMA30"], bool)
        assert isinstance(result["aboveMA60"], bool)
        assert isinstance(result["aboveMA200"], bool)

    def test_max_drawdown_is_negative(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        # Max drawdown should be negative (or zero if no decline)
        assert result["maxDD"] <= 0

    def test_price_is_positive(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        assert result["price"] > 0

    def test_values_are_rounded(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        # return6m rounded to 2 decimals
        assert result["return6m"] == round(result["return6m"], 2)
        # sortino rounded to 2 decimals
        assert result["sortino"] == round(result["sortino"], 2)
        # zScore rounded to 2 decimals
        assert result["zScore"] == round(result["zScore"], 2)
        # slope rounded to 3 decimals
        assert result["slope"] == round(result["slope"], 3)
        # maxDD rounded to 1 decimal
        assert result["maxDD"] == round(result["maxDD"], 1)

    def test_no_name_map_uses_ticker(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
            name_map=None,
        )
        assert result["name"] == "SPY"

    def test_no_category_map_not_etf(self, sample_prices, sample_maps):
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
            category_map=None,
        )
        assert result["isETF"] is False
        assert result["category"] == ""

    def test_unknown_ticker_defaults(self, sample_prices):
        result = calculate_metrics(
            sample_prices, "UNKNOWN",
            sector_map={},
            country_map={},
        )
        assert result["sector"] == "Other"
        assert result["country"] == "Other"

    def test_uptrending_prices(self):
        """An uptrending price series should have positive return and slope."""
        np.random.seed(100)
        dates = pd.bdate_range(start="2024-01-01", periods=300)
        # Strong uptrend: 0.2% daily return
        prices = 100 * np.cumprod(1 + np.full(300, 0.002) + np.random.normal(0, 0.005, 300))
        series = pd.Series(prices, index=dates, name="UP")

        result = calculate_metrics(series, "UP", {"UP": "Test"}, {"UP": "US"})
        assert result["return6m"] > 0
        assert result["slope"] > 0

    def test_downtrending_prices(self):
        """A downtrending price series should have negative return and slope."""
        np.random.seed(100)
        dates = pd.bdate_range(start="2024-01-01", periods=300)
        # Strong downtrend: -0.2% daily return
        prices = 100 * np.cumprod(1 + np.full(300, -0.002) + np.random.normal(0, 0.005, 300))
        series = pd.Series(prices, index=dates, name="DOWN")

        result = calculate_metrics(series, "DOWN", {"DOWN": "Test"}, {"DOWN": "US"})
        assert result["return6m"] < 0
        assert result["slope"] < 0

    def test_prices_with_nan_values(self, sample_maps):
        """Prices with NaN values should be handled (NaN rows dropped)."""
        np.random.seed(42)
        dates = pd.bdate_range(start="2024-01-01", periods=300)
        prices = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.015, 300))
        series = pd.Series(prices, index=dates, name="SPY")
        # Insert some NaN values
        series.iloc[50] = np.nan
        series.iloc[100] = np.nan

        result = calculate_metrics(
            series, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
        )
        # Should still return a result since 298 valid days > 252
        assert result is not None

    def test_cash_category_is_etf(self, sample_prices):
        """Cash category should also be marked as isETF=True."""
        result = calculate_metrics(
            sample_prices, "SHY",
            {"SHY": "Cash"}, {"SHY": "Cash"},
            name_map={"SHY": "iShares Treasury"},
            category_map={"SHY": "Cash"},
        )
        assert result["isETF"] is True

    def test_equity_category_not_etf(self, sample_prices):
        """Equity category should be marked as isETF=False."""
        result = calculate_metrics(
            sample_prices, "AAPL",
            {"AAPL": "US Tech"}, {"AAPL": "US"},
            name_map={"AAPL": "Apple Inc."},
            category_map={"AAPL": "Equity"},
        )
        assert result["isETF"] is False


# ======================== TESTS: calculate_correlations ========================


class TestCalculateCorrelations:
    """Tests for the correlation calculation function."""

    def test_returns_dict(self, multi_ticker_prices):
        tickers = ["SPY", "QQQ", "GLD"]
        result = calculate_correlations(multi_ticker_prices, tickers)
        assert isinstance(result, dict)

    def test_correct_number_of_pairs(self, multi_ticker_prices):
        tickers = ["SPY", "QQQ", "GLD"]
        result = calculate_correlations(multi_ticker_prices, tickers)
        # 3 tickers -> 3 pairs: SPY-QQQ, SPY-GLD, QQQ-GLD
        assert len(result) == 3

    def test_key_format(self, multi_ticker_prices):
        tickers = ["SPY", "QQQ", "GLD"]
        result = calculate_correlations(multi_ticker_prices, tickers)
        assert "SPY-QQQ" in result
        assert "SPY-GLD" in result
        assert "QQQ-GLD" in result

    def test_correlation_range(self, multi_ticker_prices):
        tickers = ["SPY", "QQQ", "GLD"]
        result = calculate_correlations(multi_ticker_prices, tickers)
        for key, corr in result.items():
            assert -1 <= corr <= 1, f"Correlation {key}={corr} out of range"

    def test_correlated_tickers_high_corr(self, multi_ticker_prices):
        """SPY and QQQ (constructed to be correlated) should have high correlation."""
        tickers = ["SPY", "QQQ", "GLD"]
        result = calculate_correlations(multi_ticker_prices, tickers)
        assert result["SPY-QQQ"] > 0.5

    def test_values_rounded_to_2(self, multi_ticker_prices):
        tickers = ["SPY", "QQQ", "GLD"]
        result = calculate_correlations(multi_ticker_prices, tickers)
        for key, corr in result.items():
            assert corr == round(corr, 2)

    def test_single_ticker_empty_result(self, multi_ticker_prices):
        result = calculate_correlations(multi_ticker_prices, ["SPY"])
        assert result == {}

    def test_two_tickers_one_pair(self, multi_ticker_prices):
        result = calculate_correlations(multi_ticker_prices, ["SPY", "QQQ"])
        assert len(result) == 1
        assert "SPY-QQQ" in result


# ======================== TESTS: fetch_data ========================


class TestFetchData:
    """Tests for the data fetching function (mocked)."""

    def test_fetch_data_returns_dataframe(self, mocker):
        """Test that fetch_data returns a DataFrame when yfinance succeeds."""
        dates = pd.bdate_range(start="2023-01-01", periods=100)
        mock_data = pd.DataFrame(
            {"SPY": np.random.rand(100) * 400 + 300},
            index=dates,
        )
        # yf.download() returns an object that is indexed with ['Close']
        mock_result = pd.DataFrame(
            {"Close": mock_data["SPY"]},
            index=dates,
        )
        # Create a mock that supports ['Close'] indexing returning mock_data
        mock_download = mocker.patch("mom_gen.yf.download")
        mock_download.return_value = {"Close": mock_data}

        result = fetch_data(["SPY"])
        assert result is not None
        mock_download.assert_called_once()

    def test_fetch_data_returns_none_on_error(self, mocker):
        """Test that fetch_data returns None when yfinance raises."""
        mocker.patch("mom_gen.yf.download", side_effect=Exception("Network error"))
        result = fetch_data(["SPY"])
        assert result is None


# ======================== TESTS: generate_html ========================


class TestGenerateHTML:
    """Tests for the HTML generation function."""

    def test_generates_valid_html(self):
        etf_data = [
            {
                "ticker": "SPY",
                "name": "SPDR S&P 500",
                "sector": "US Broad Market",
                "country": "US",
                "category": "ETF",
                "isETF": True,
                "price": 450.0,
                "return6m": 12.5,
                "sortino": 1.5,
                "weeksDown": 3,
                "zScore": 0.8,
                "slope": 0.15,
                "aboveMA30": True,
                "aboveMA60": True,
                "aboveMA200": True,
                "maxDD": -8.5,
            }
        ]
        correlations = {}
        html = generate_html(etf_data, correlations, "2024-06-15")
        assert html is not None
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html

    def test_html_contains_data(self):
        etf_data = [
            {
                "ticker": "GLD",
                "name": "SPDR Gold",
                "sector": "Precious Metals",
                "country": "Commodities",
                "category": "ETF",
                "isETF": True,
                "price": 180.0,
                "return6m": 8.0,
                "sortino": 1.2,
                "weeksDown": 4,
                "zScore": 0.5,
                "slope": 0.1,
                "aboveMA30": True,
                "aboveMA60": True,
                "aboveMA200": True,
                "maxDD": -5.0,
            }
        ]
        html = generate_html(etf_data, {}, "2024-06-15")
        # The etf data should be embedded as JSON
        assert "GLD" in html
        assert "SPDR Gold" in html
        assert "Precious Metals" in html

    def test_html_contains_generation_date(self):
        html = generate_html([], {}, "2024-06-15")
        assert "2024-06-15" in html

    def test_html_contains_correlations(self):
        etf_data = []
        correlations = {"SPY-QQQ": 0.85, "SPY-GLD": 0.12}
        html = generate_html(etf_data, correlations, "2024-06-15")
        assert "SPY-QQQ" in html
        assert "0.85" in html

    def test_html_has_required_tabs(self):
        html = generate_html([], {}, "2024-06-15")
        assert "Screener" in html
        assert "Portfolio" in html
        assert "Strategy" in html
        assert "Settings" in html

    def test_html_has_title(self):
        html = generate_html([], {}, "2024-06-15")
        assert "Momentum Portfolio Framework" in html

    def test_html_multiple_etfs(self):
        etf_data = [
            {
                "ticker": f"ETF{i}",
                "name": f"ETF Number {i}",
                "sector": "Test",
                "country": "US",
                "category": "ETF",
                "isETF": True,
                "price": 100.0 + i,
                "return6m": 5.0 + i,
                "sortino": 1.0,
                "weeksDown": 2,
                "zScore": 0.5,
                "slope": 0.1,
                "aboveMA30": True,
                "aboveMA60": True,
                "aboveMA200": True,
                "maxDD": -3.0,
            }
            for i in range(10)
        ]
        html = generate_html(etf_data, {}, "2024-06-15")
        for i in range(10):
            assert f"ETF{i}" in html


# ======================== TESTS: Integration ========================


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_load_and_calculate_pipeline(self, sample_csv, sample_prices):
        """Test the pipeline from loading CSV to calculating metrics."""
        tickers, sector_map, country_map, name_map, highvol_map, category_map, regions_map = load_etf_universe(sample_csv)

        # Use SPY from the loaded universe
        assert "SPY" in tickers

        result = calculate_metrics(
            sample_prices, "SPY",
            sector_map, country_map, name_map, category_map,
        )
        assert result is not None
        assert result["ticker"] == "SPY"
        assert result["name"] == "SPDR S&P 500"
        assert result["sector"] == "US Broad Market"

    def test_metrics_to_html_pipeline(self, sample_prices, sample_maps):
        """Test from metrics calculation to HTML generation."""
        result = calculate_metrics(
            sample_prices, "SPY",
            sample_maps["sector_map"],
            sample_maps["country_map"],
            sample_maps["name_map"],
            sample_maps["category_map"],
        )
        assert result is not None

        html = generate_html([result], {}, "2024-06-15")
        assert "SPY" in html
        assert "SPDR S&P 500" in html

    def test_full_pipeline_with_correlations(self, multi_ticker_prices, sample_maps):
        """Test full pipeline: metrics + correlations + HTML."""
        etf_data = []
        for ticker in ["SPY", "QQQ", "GLD"]:
            result = calculate_metrics(
                multi_ticker_prices[ticker],
                ticker,
                sample_maps["sector_map"],
                sample_maps["country_map"],
                sample_maps["name_map"],
                sample_maps["category_map"],
            )
            if result:
                etf_data.append(result)

        correlations = calculate_correlations(
            multi_ticker_prices, ["SPY", "QQQ", "GLD"]
        )

        html = generate_html(etf_data, correlations, "2024-06-15")
        assert len(etf_data) == 3
        assert len(correlations) == 3
        assert "SPY" in html
        assert "QQQ" in html
        assert "GLD" in html


# ======================== TESTS: Edge Cases ========================


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_constant_prices(self):
        """Constant prices should produce zero return and slope."""
        dates = pd.bdate_range(start="2024-01-01", periods=300)
        prices = pd.Series(np.full(300, 100.0), index=dates, name="FLAT")

        result = calculate_metrics(prices, "FLAT", {"FLAT": "Test"}, {"FLAT": "US"})
        assert result is not None
        assert result["return6m"] == 0.0
        assert result["slope"] == 0.0
        assert result["sortino"] == 0  # No variance

    def test_very_volatile_prices(self):
        """Very volatile prices should still produce valid results."""
        np.random.seed(42)
        dates = pd.bdate_range(start="2024-01-01", periods=300)
        # High volatility: 5% daily std
        prices = 100 * np.cumprod(1 + np.random.normal(0, 0.05, 300))
        prices = np.maximum(prices, 0.01)  # Keep prices positive
        series = pd.Series(prices, index=dates, name="VOL")

        result = calculate_metrics(series, "VOL", {"VOL": "Test"}, {"VOL": "US"})
        assert result is not None
        assert isinstance(result["sortino"], float)
        assert isinstance(result["maxDD"], float)

    def test_exactly_252_days(self):
        """Exactly 252 days of data should be accepted."""
        np.random.seed(42)
        dates = pd.bdate_range(start="2024-01-01", periods=252)
        prices = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.015, 252))
        series = pd.Series(prices, index=dates, name="EXACT")

        result = calculate_metrics(series, "EXACT", {"EXACT": "Test"}, {"EXACT": "US"})
        assert result is not None

    def test_251_days_returns_none(self):
        """251 days (just under minimum) should return None."""
        np.random.seed(42)
        dates = pd.bdate_range(start="2024-01-01", periods=251)
        prices = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.015, 251))
        series = pd.Series(prices, index=dates, name="SHORT")

        result = calculate_metrics(series, "SHORT", {"SHORT": "Test"}, {"SHORT": "US"})
        assert result is None

    def test_empty_csv(self, tmp_path):
        """Empty CSV (headers only) should return empty lists."""
        csv_content = "Name,Symbol,Region,Category,Subcategory,High Vol\n"
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text(csv_content)

        tickers, *_ = load_etf_universe(str(csv_file))
        assert len(tickers) == 0

    def test_correlations_with_identical_prices(self):
        """Identical price series should have correlation of 1.0."""
        dates = pd.bdate_range(start="2024-01-01", periods=300)
        np.random.seed(42)
        returns = np.random.normal(0.001, 0.01, 300)
        prices_a = 100 * np.cumprod(1 + returns)
        df = pd.DataFrame({"A": prices_a, "B": prices_a}, index=dates)

        result = calculate_correlations(df, ["A", "B"])
        assert result["A-B"] == 1.0

    def test_clean_symbol_empty_string(self):
        """Empty string should be returned as-is."""
        assert clean_symbol("") == ""

    def test_large_number_of_correlations(self):
        """Test with many tickers to verify O(n^2) pairs."""
        np.random.seed(42)
        dates = pd.bdate_range(start="2024-01-01", periods=100)
        n_tickers = 10
        data = {f"T{i}": np.random.rand(100) * 100 for i in range(n_tickers)}
        df = pd.DataFrame(data, index=dates)

        result = calculate_correlations(df, [f"T{i}" for i in range(n_tickers)])
        expected_pairs = n_tickers * (n_tickers - 1) // 2  # 45 pairs
        assert len(result) == expected_pairs
