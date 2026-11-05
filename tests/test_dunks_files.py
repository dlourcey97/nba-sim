"""Dunks CSV intake matches names and does not rewrite an identical day."""

from __future__ import annotations

from datetime import date

from ingest.dunks_files import load_csv, normalize_name


def test_blank_id_matches_the_roster_name(tmp_path):
    source = tmp_path / "minutes.csv"
    source.write_text(
        "name,team,minutes,pts,reb,ast,stl,blk,tov,oreb,dreb,fg3a\n"
        "Bobby Portis Jr.,MIA,19,9,5,1,1,0,1,1,4,4\n"
        "Nobody,MIA,4,1,1,0,0,0,0,0,1,1\n",
        encoding="utf-8",
    )
    names = {(normalize_name("Bobby Portis Jr."), "MIA"): 1626171}
    report = load_csv(
        source,
        tmp_path / "dunks",
        as_of=date(2026, 11, 5),
        names=names,
    )
    assert report.kind == "minutes"
    assert report.status == "wrote"
    assert report.rows == 1
    assert report.unmatched == ["Nobody (MIA)"]
    again = load_csv(source, tmp_path / "dunks", as_of=date(2026, 11, 5), names=names)
    assert again.status == "already"


def test_epm_id_is_kept(tmp_path):
    source = tmp_path / "epm_2026-11-05.csv"
    header = (
        "season,nba_id,name,team,p_mpg,p_usg,oepm,depm,epm,p_pts_100,p_tspct,"
        "p_fg2a_100,p_fg2pct,p_fg3a_100,p_fg3pct,p_fta_100,p_ftpct,p_orb_100,"
        "p_drb_100,p_ast_100,p_tov_100,p_stl_100,p_blk_100"
    )
    source.write_text(
        header + "\n2027,1641705,Victor Wembanyama,SAS,30,0.3,4,5,9,30,0.6,"
        "12,0.55,8,0.35,8,0.8,2,8,4,3,1,3\n",
        encoding="utf-8",
    )
    report = load_csv(source, tmp_path / "dunks", as_of=date(2026, 11, 5))
    assert report.status == "wrote"
    assert report.rows == 1
    assert report.unmatched == []
    assert report.as_of == "2026-11-05"
