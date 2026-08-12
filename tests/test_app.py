from streamlit.testing.v1 import AppTest


def test_initial_screen_has_inputs_and_no_report():
    at = AppTest.from_file("../app.py").run(timeout=20)
    assert not at.exception
    assert at.selectbox[0].options == ["Mutual Fund", "PMS", "AIF"]
    assert at.button(key="search").label == "Find product"
    assert at.button(key="analyze").label == "Analyze"
    assert at.button(key="analyze").disabled is True
