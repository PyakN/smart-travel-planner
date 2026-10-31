import asyncio
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.ingest import wiki
from app.ingest.wiki import (
    DESCRIPTION_MAX_CHARS,
    SPARQL_BATCH,
    Photo,
    WikidataInfo,
    article_title,
    clean_extract,
    description,
    fetch_photos,
    fetch_wikidata,
    parse_extracts,
    parse_imageinfo,
    parse_sparql,
    photo_file,
    sparql_query,
    wikipedia_languages,
)

TRINDADE = "https://commons.wikimedia.org/wiki/Special:FilePath/Teatro%20da%20Trindade%202017.jpg"


def binding(qid: str, **values: str) -> dict[str, Any]:
    item = {"item": {"value": f"http://www.wikidata.org/entity/{qid}"}}
    return item | {key: {"value": value} for key, value in values.items()}


def imageinfo_page(title: str, *, artist: str = "<a href='x'>Jane</a>") -> dict[str, Any]:
    name = title.removeprefix("File:").replace(" ", "_")
    return {
        "title": title,
        "imageinfo": [
            {
                "thumburl": f"https://thumb.wikimedia.org/x/500px-{name}?utm_source=commons",
                "descriptionurl": f"https://commons.wikimedia.org/wiki/File:{name}",
                "extmetadata": {
                    "Artist": {"value": artist},
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                },
            }
        ],
    }


class TestSparql:
    def test_query_skips_invalid_ids(self) -> None:
        query = sparql_query(["Q1", "Q2'}", "X3"])
        assert "VALUES ?item { wd:Q1 }" in query

    def test_first_image_and_article_win(self) -> None:
        payload = {
            "results": {
                "bindings": [
                    binding(
                        "Q1",
                        image=TRINDADE,
                        description="theatre in Lisbon",
                        article="https://en.wikipedia.org/wiki/Teatro_da_Trindade",
                        wikipedias="7",
                    ),
                    binding(
                        "Q1", image="https://commons.wikimedia.org/wiki/Special:FilePath/B.jpg"
                    ),
                    binding("Q2"),
                ]
            }
        }
        assert parse_sparql(payload) == {
            "Q1": WikidataInfo(
                "Teatro da Trindade 2017.jpg", "theatre in Lisbon", "Teatro_da_Trindade", 7
            ),
            "Q2": WikidataInfo(None, None, None, 0),  # in no Wikipedia
        }


class TestImageinfo:
    def test_thumbnail_page_and_credit(self) -> None:
        payload = {"query": {"pages": [imageinfo_page("File:Teatro da Trindade 2017.jpg")]}}
        assert parse_imageinfo(payload) == {
            "Teatro da Trindade 2017.jpg": Photo(
                url="https://thumb.wikimedia.org/x/500px-Teatro_da_Trindade_2017.jpg",
                page_url="https://commons.wikimedia.org/wiki/File:Teatro_da_Trindade_2017.jpg",
                credit="Jane, CC BY-SA 4.0",
            )
        }

    def test_missing_files_and_normalized_titles(self) -> None:
        payload = {
            "query": {
                "normalized": [{"from": "File:a_b.jpg", "to": "File:A b.jpg"}],
                "pages": [
                    imageinfo_page("File:A b.jpg", artist="Jos&eacute; <i>Silva</i>"),
                    {"title": "File:Gone.jpg", "missing": True},
                ],
            }
        }
        photos = parse_imageinfo(payload)
        assert set(photos) == {"A b.jpg"}
        assert photos["A b.jpg"].credit == "José Silva, CC BY-SA 4.0"

    def test_urls_are_left_out_of_credits(self) -> None:
        artist = "Filipe Rocha,user:sacavem (pt) http://pt.wikipedia.org/wiki/Usu%C3%A1rio:Sacavem"
        payload = {"query": {"pages": [imageinfo_page("File:X.jpg", artist=artist)]}}
        credit = parse_imageinfo(payload)["X.jpg"].credit
        assert credit == "Filipe Rocha,user:sacavem (pt), CC BY-SA 4.0"


class TestExtracts:
    def test_asides_are_removed(self) -> None:
        text = (
            "The Santa Justa Lift (Portuguese: Elevador de Santa Justa, pronounced [x (y)]), "
            "also called Carmo Lift, is an elevator in Lisbon. It connects the Baixa (lower "
            "town) with Largo do Carmo."
        )
        assert clean_extract(text) == (
            "The Santa Justa Lift, also called Carmo Lift, is an elevator in Lisbon. "
            "It connects the Baixa with Largo do Carmo."
        )

    def test_long_text_is_cut_at_a_sentence(self) -> None:
        sentence = "A sentence of moderate length about a place. "
        cleaned = clean_extract(sentence * 20)
        assert cleaned is not None
        assert len(cleaned) <= DESCRIPTION_MAX_CHARS
        assert cleaned.endswith("place.")

    def test_redirects_keep_the_requested_title(self) -> None:
        payload = {
            "query": {
                "normalized": [{"from": "Santa_Justa_Lift", "to": "Santa Justa Lift"}],
                "redirects": [{"from": "Santa Justa Lift", "to": "Elevador de Santa Justa"}],
                "pages": [{"title": "Elevador de Santa Justa", "extract": "An elevator."}],
            }
        }
        extracts = parse_extracts(payload)
        assert extracts["Santa Justa Lift"] == extracts["Elevador de Santa Justa"] == "An elevator."


class TestChoosing:
    INFO = WikidataInfo("Wikidata.jpg", "church in Lisbon, Portugal", "Igreja_X", 12)

    def test_wikidata_image_wins(self) -> None:
        assert photo_file({"wikimedia_commons": "File:Osm.jpg"}, self.INFO) == "Wikidata.jpg"

    @pytest.mark.parametrize(
        ("tags", "expected"),
        [
            ({"wikimedia_commons": "File:osm_photo.jpg"}, "Osm photo.jpg"),
            ({"wikimedia_commons": "Category:Churches"}, None),
            (
                {"image": "https://commons.wikimedia.org/wiki/File:Some%20Photo.jpg"},
                "Some Photo.jpg",
            ),
            ({"image": "https://upload.wikimedia.org/wikipedia/commons/a/ab/X.jpg"}, "X.jpg"),
            ({"image": "http://geoportal.example.pt/id26.jpg"}, None),  # not from Commons
            ({}, None),
        ],
    )
    def test_osm_tags(self, tags: dict[str, str], expected: str | None) -> None:
        assert photo_file(tags, None) == expected

    def test_article_from_wikidata_or_english_wikipedia_tag(self) -> None:
        assert article_title({}, self.INFO) == "Igreja X"
        assert article_title({"wikipedia": "en:Galveias Palace"}, None) == "Galveias Palace"
        assert article_title({"wikipedia": "pt:Palácio Galveias"}, None) is None

    def test_wikipedia_languages_from_wikidata_or_wikipedia_tag(self) -> None:
        assert wikipedia_languages({"wikipedia": "pt:Igreja X"}, self.INFO) == 12
        assert wikipedia_languages({"wikipedia": "pt:Palácio Galveias"}, None) == 1
        assert wikipedia_languages({}, None) == 0

    def test_description_preference(self) -> None:
        assert description({}, self.INFO, {"Igreja X": "A church."}) == "A church."
        assert description({}, self.INFO, {}) == "Church in Lisbon, Portugal."
        assert description({"description:en": "A mural."}, None, {}) == "A mural."
        assert description({"description": "Mural de azulejos."}, None, {}) is None


def test_wikidata_is_fetched_in_batches() -> None:
    batches: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["User-Agent"].startswith("smart-travel-planner/")
        query = parse_qs(request.content.decode())["query"][0]
        batches.append(query)
        return httpx.Response(200, json={"results": {"bindings": [binding("Q1", image=TRINDADE)]}})

    async def run() -> dict[str, WikidataInfo]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_wikidata(client, [f"Q{i}" for i in range(1, SPARQL_BATCH + 2)])

    found = asyncio.run(run())
    assert len(batches) == 2
    assert found["Q1"].image == "Teatro da Trindade 2017.jpg"


def test_photo_requests_name_files_once() -> None:
    titles: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        titles.extend(request.url.params["titles"].split("|"))
        return httpx.Response(200, json={"query": {"pages": [imageinfo_page("File:A b.jpg")]}})

    async def run() -> dict[str, Photo]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_photos(client, ["a_b.jpg", "A b.jpg", "File:A_b.jpg"])

    assert set(asyncio.run(run())) == {"A b.jpg"}
    assert titles == ["File:A b.jpg"]


@pytest.fixture
def no_retry_pause(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(wiki, "RETRY_DELAY_S", 0)


def test_throttling_and_timeouts_are_retried(no_retry_pause: None) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ReadTimeout("slow", request=request)
        if attempts == 2:
            return httpx.Response(429)
        return httpx.Response(200, json={"query": {"pages": [imageinfo_page("File:A.jpg")]}})

    async def run() -> dict[str, Photo]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_photos(client, ["A.jpg"])

    assert set(asyncio.run(run())) == {"A.jpg"}
    assert attempts == 3


def test_http_errors_propagate(no_retry_pause: None) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await fetch_photos(client, ["A.jpg"])

    with pytest.raises(httpx.HTTPStatusError):
        asyncio.run(run())
    assert calls == wiki.ATTEMPTS
