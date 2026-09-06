from streamlit.testing.v1 import AppTest


def test_initial_screen_has_inputs_and_no_report():
    at = AppTest.from_file("../app.py").run(timeout=20)
    assert not at.exception
    assert at.selectbox[0].options == ["Mutual Fund", "PMS", "AIF"]
    assert at.button(key="search").label == "Find product"
    assert at.button(key="analyze").label == "Analyze"
    assert at.button(key="analyze").disabled is True


def test_aif_input_exposes_structured_dated_cash_flow_editor():
    at = AppTest.from_file("../app.py").run(timeout=20)
    at.selectbox(key="product_type").set_value("AIF").run(timeout=20)

    assert not at.exception
    assert len(at.dataframe) == 1
    assert "positive amounts" in at.info[0].value
