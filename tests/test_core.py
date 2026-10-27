import contextlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from vitaldock.archive import InputError, inputs
from vitaldock.cli import main
from vitaldock.huawei import parse
from vitaldock.model import digest, instant
from vitaldock.store import Vault

T = 1792886400000


def point(key="DATA_POINT_DYNAMIC_HEARTRATE", value="72", start=T, end=T + 60000, **extra):
    return {"key": key, "value": value, "startTime": start, "endTime": end,
            "unit": "0", **extra}


def export(points=None, **extra):
    return json.dumps([{"type": 7, "deviceCode": 999, "timeZone": "+0800",
                        "samplePoints": points if points is not None else [point()],
                        **extra}]).encode()


class ParserTests(unittest.TestCase):
    def test_heart_rate_times_and_units(self):
        result = parse(export())
        self.assertEqual(result.issues, [])
        row = result.records[0]
        self.assertEqual((row["metric"], row["value"], row["unit"]), ("heart_rate", 72, "bpm"))
        self.assertEqual(row["start_ms"], T)
        self.assertEqual(row["source_utc_offset"], "+08:00")
        self.assertEqual(row["pointer"], "/0/samplePoints/0")

    def test_bom_and_single_object(self):
        self.assertEqual(len(parse(b"\xef\xbb\xbf" + export()).records), 1)
        self.assertEqual(len(parse(json.dumps(json.loads(export())[0]).encode()).records), 1)

    def test_sleep_stages_and_true_interval(self):
        row = parse(export([point("PROFESSIONAL_SLEEP_DREAM", "ignored")])).records[0]
        self.assertEqual((row["metric"], row["value"], row["end_ms"]), ("sleep_stage", "rem", T+60000))

    def test_body_composition_does_not_invent_missing_values(self):
        row = parse(export([point("WEIGHT_BODYFAT_BROAD", '{"bodyWeight":68.5}')]))
        self.assertEqual(len(row.records), 1)
        self.assertEqual(row.records[0]["metric"], "body_weight")
        self.assertEqual(row.records[0]["value"], 68.5)

    def test_separate_subjects(self):
        a = parse(export(subUser="person-a")).records[0]
        b = parse(export(subUser="person-b")).records[0]
        self.assertNotEqual(a["subject_id"], b["subject_id"])
        self.assertNotIn("person-a", a["subject_id"])
        weight = parse(export([point("WEIGHT_BODYFAT_BROAD",
                                     '{"bodyWeight":68,"extendAttribute":"family-b"}')],
                              subUser=None))
        self.assertNotEqual(weight.records[0]["subject_id"], "self")

    def test_unusable_values_reported(self):
        for value in ("NaN", "Infinity", "-1", "301", "instructions", True, None, {}):
            with self.subTest(value=value):
                result = parse(export([point(value=value)]))
                self.assertEqual(result.records, [])
                self.assertEqual(result.issues[0]["severity"], "error")

    def test_unsupported_unit_not_guessed(self):
        result = parse(export([point(unit="beats/second")]))
        self.assertEqual(result.records, [])
        self.assertEqual(result.issues[0]["code"], "unsupported_unit")

    def test_invalid_timestamps_not_auto_repaired(self):
        for data in (point(start=T*1000000), point(start=T//1000),
                     point(end=T-1), point(start=True), point(timeZone="Beijing")):
            with self.subTest(data=data):
                self.assertEqual(parse(export([data])).records, [])

    def test_unknown_and_invalid_json_reported(self):
        self.assertEqual(parse(b'{"partTimeMap":{bad:1},}').issues[0]["code"], "invalid_json")
        self.assertEqual(parse(export([point("UNKNOWN")] )).issues[0]["code"],
                         "unsupported_sample_key")

    def test_spo2_percent_not_fraction(self):
        result = parse(export([point("BLOOD_OXYGEN_SATURATION", "98")]))
        self.assertEqual((result.records[0]["value"], result.records[0]["unit"]), (98, "%"))

    def test_all_sport_basic_infos_summed_without_calorie_guess(self):
        data = [{"recordDay": 20261025, "sportDataUserData": [{
            "startTime": T, "endTime": T+120000, "timeZone": "+0800", "sportType": 5,
            "sportBasicInfos": [{"steps": 12, "calorie": 20, "distance": 8},
                                {"steps": 15, "calorie": 25, "distance": 10}]}]}]
        result = parse(json.dumps(data).encode())
        self.assertEqual(len(result.records), 1)
        self.assertEqual(result.records[0]["value"], 27)
        self.assertEqual(result.records[0]["end_ms"], T+120000)
        self.assertIn("unverified", result.issues[0]["code"])

    def test_workout_duration_uses_elapsed_time(self):
        data = [{"motionPathData": [{"startTime": T, "endTime": T+3600000,
                                     "sportType": 2, "attribute": "SYNTHETIC"}]}]
        result = parse(json.dumps(data).encode())
        self.assertEqual(result.records[0]["value"], 3600)
        self.assertEqual(result.records[0]["qualifiers"]["duration_basis"], "elapsed_interval")
        self.assertNotIn("attribute", result.records[0])


class VaultTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.vault = Vault(self.root / "vault")
        self.file = self.root / "input.json"
        self.file.write_bytes(export())

    def tearDown(self):
        self.temp.cleanup()

    def test_import_reimport_and_raw_integrity(self):
        a = self.vault.import_huawei(self.file)
        b = self.vault.import_huawei(self.file)
        self.assertEqual((a["records_inserted"], b["records_inserted"]), (1, 0))
        sha = digest(self.file.read_bytes())
        self.assertEqual((self.vault.root / "objects" / sha).read_bytes(), self.file.read_bytes())
        result = self.vault.query(subject="self")
        self.assertEqual(result["records"][0]["provenance"][0]["object_sha256"], sha)

    def test_provenance_accumulates_across_export_files(self):
        self.vault.import_huawei(self.file)
        self.file.write_bytes(export() + b"\n")
        self.vault.import_huawei(self.file)
        rows = self.vault.query(subject="self")["records"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(rows[0]["provenance"]), 2)

    def test_conflicting_values_not_overwritten(self):
        self.vault.import_huawei(self.file)
        self.file.write_bytes(export([point(value="73")]))
        self.vault.import_huawei(self.file)
        self.assertEqual(len(self.vault.query(subject="self")["records"]), 2)

    def test_pagination_with_equal_timestamps(self):
        self.file.write_bytes(export([point(value=str(n)) for n in range(60, 65)]))
        self.vault.import_huawei(self.file)
        result = self.vault.query(subject="self", limit=2)
        ids = [x["id"] for x in result["records"]]
        while result["has_more"]:
            result = self.vault.query(subject="self", limit=2, cursor=result["next_cursor"])
            ids.extend(x["id"] for x in result["records"])
        self.assertEqual(len(ids), 5)
        self.assertEqual(len(set(ids)), 5)

    def test_query_half_open_range_and_utc_offset(self):
        self.file.write_bytes(export([point(start=T), point(start=T+60000,end=T+120000)]))
        self.vault.import_huawei(self.file)
        from vitaldock.model import iso_utc
        rows = self.vault.query(subject="self", since=iso_utc(T), until=iso_utc(T+60000))
        self.assertEqual(len(rows["records"]), 1)
        self.assertEqual(instant("2026-10-25T08:00:00+08:00"), instant("2026-10-25T00:00:00Z"))

    def test_query_validation_and_subject_isolation(self):
        self.vault.import_huawei(self.file)
        for kwargs in ({"limit": 501}, {"limit": True}, {"metric": "bogus"},
                       {"cursor": "1:drop table records"}, {"since": "2026-10-25"},
                       {"since":"2026-10-25T00:00:00Z", "until":"2026-10-24T00:00:00Z"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.vault.query(subject="self", **kwargs)
        self.assertEqual(self.vault.query(subject="other")["records"], [])
        row = self.vault.query(subject="self")["records"][0]
        with self.assertRaises(ValueError):
            self.vault.provenance(row["id"], subject="other")

    def test_strict_rolls_back_prior_files_in_same_import(self):
        folder = self.root / "folder"
        folder.mkdir()
        (folder / "a.json").write_bytes(export())
        (folder / "b.json").write_bytes(export([point("UNKNOWN")]))
        with self.assertRaises(ValueError):
            self.vault.import_huawei(folder, strict=True)
        self.assertEqual(self.vault.coverage()["series"], [])

    def test_invalid_json_reported_and_preserved(self):
        self.file.write_bytes(b"malformed-private-bytes")
        report = self.vault.import_huawei(self.file)
        self.assertEqual(report["status"], "no_supported_records")
        self.assertEqual(report["issues"], {"invalid_json": 1})
        self.assertNotIn("private-bytes", json.dumps(report))
        self.assertEqual(len(list((self.vault.root / "objects").iterdir())), 1)

    def test_raw_tampering_detected(self):
        self.vault.import_huawei(self.file)
        path = next((self.vault.root / "objects").iterdir())
        path.write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            self.vault.import_huawei(self.file)

    def test_read_queries_do_not_modify_database(self):
        self.vault.import_huawei(self.file)
        before = digest(self.vault.database.read_bytes())
        self.vault.query(subject="self")
        self.vault.coverage("self")
        self.assertEqual(digest(self.vault.database.read_bytes()), before)

    def test_sqlite_special_path_characters(self):
        vault = Vault(self.root / ("空间 #" if os.name == "nt" else "空间?#"))
        vault.import_huawei(self.file)
        self.assertEqual(len(vault.query(subject="self")["records"]), 1)

    def test_cli_exit_and_error_contract(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        self.file.write_bytes(b"bad-json")
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["--vault", str(self.vault.root), "import-huawei", str(self.file)])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(stdout.getvalue())["status"], "no_supported_records")
        self.assertEqual(stderr.getvalue(), "")


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def zip(self, names):
        path = self.root / "source.zip"
        with zipfile.ZipFile(path, "w") as archive:
            for name in names:
                archive.writestr(name, export())
        return path

    def test_zip_read_without_extraction(self):
        path = self.zip(["Health detail/heart.json"])
        self.assertEqual(list(inputs(path))[0][1], export())
        self.assertFalse((self.root / "Health detail").exists())
        (self.root / "UPPER.JSON").write_bytes(export())
        self.assertEqual(len(list(inputs(self.root))), 1)

    def test_zip_traversal_rejected(self):
        for name in ("../outside.json", "/abs.json", "C:/bad.json", "..\\bad.json"):
            with self.subTest(name=name), self.assertRaises(InputError):
                list(inputs(self.zip([name])))

    def test_zip_symlink_rejected(self):
        path = self.root / "source.zip"
        info = zipfile.ZipInfo("link.json")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr(info, "outside")
        with self.assertRaises(InputError):
            list(inputs(path))

    def test_encrypted_zip_gives_local_decryption_instruction(self):
        path = self.zip(["health.json"])
        data = bytearray(path.read_bytes())
        data[6] |= 1
        index = data.index(b"PK\x01\x02")
        data[index+8] |= 1
        path.write_bytes(data)
        with self.assertRaisesRegex(InputError, "decrypt locally"):
            list(inputs(path))

    def test_size_budget(self):
        path = self.zip(["health.json"])
        with patch("vitaldock.archive.MAX_FILE", 1), self.assertRaises(InputError):
            list(inputs(path))

    def test_no_json_error(self):
        with self.assertRaises(InputError):
            list(inputs(self.root))


if __name__ == "__main__":
    unittest.main()
