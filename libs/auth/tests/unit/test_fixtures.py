def test_fixture_metadata():
    import json
    from pathlib import Path
    fixtures = json.loads(
        (Path(__file__).parent.parent / "fixtures" / "jwt_tokens.json").read_text()
    )
    assert fixtures["token_types"]["valid_admin"]["roles"] == ["Admin", "Learner"]
    assert fixtures["token_types"]["expired"]["exp_offset_seconds"] < 0
