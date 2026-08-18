"""VPS member service tests."""

from services.vps_service import add_vps_member, list_vps_members, update_vps_member


def test_update_vps_member_name(db_session):
    member = list_vps_members(db_session, site="dc")[0]
    update_vps_member(db_session, member.id, name="Renamed Member", operator="test")
    db_session.commit()
    updated = list_vps_members(db_session, active_only=False)
    assert any(m.id == member.id and m.name == "Renamed Member" for m in updated)


def test_add_vps_member(db_session):
    add_vps_member(
        db_session,
        "New DR Staff",
        "VPS-DR99",
        "dr",
        sort_order=9,
        operator="test",
    )
    db_session.commit()
    names = [m.staff_no for m in list_vps_members(db_session, site="dr", active_only=False)]
    assert "VPS-DR99" in names
