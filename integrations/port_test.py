from integrations.port import build_run_payloads


def test_build_run_payloads_base() -> None:
    payloads = build_run_payloads(
        bag_id="bag_20260822_01",
        duration_s=8.4,
        motion="goto",
        replay_passed=True,
        replay_detail="PASS",
        elapsed_ms=421.7,
        append=False,
        spec_step_count=1,
        catalog=None,
    )
    by_blueprint = {blueprint: payload for blueprint, _, payload in payloads}
    assert "physical_prompt" in by_blueprint
    assert "change_request" in by_blueprint
    assert "factory_run" in by_blueprint
    assert "approval" in by_blueprint
    assert "twin_release" in by_blueprint
    assert "scraper_job" not in by_blueprint
    assert by_blueprint["factory_run"]["properties"]["status"] == "passed"
    assert by_blueprint["twin_release"]["properties"]["composed"] is False


def test_build_run_payloads_append_with_catalog() -> None:
    payloads = build_run_payloads(
        bag_id="bag_20260822_02",
        duration_s=9.1,
        motion="replay_trajectory",
        replay_passed=False,
        replay_detail="FAIL max error",
        elapsed_ms=812.3,
        append=True,
        spec_step_count=2,
        catalog={
            "source": "live",
            "url": "https://example.com/bottle",
            "name": "Bottle",
            "width_cm": 7.0,
            "height_cm": 24.0,
        },
    )
    by_blueprint = {blueprint: payload for blueprint, _, payload in payloads}
    assert "scraper_job" in by_blueprint
    assert "twin_release" not in by_blueprint
    assert by_blueprint["change_request"]["properties"]["stage"] == "test"
    assert by_blueprint["factory_run"]["properties"]["skill"] == "compose"
    assert by_blueprint["approval"]["properties"]["decision"] == "rejected"

