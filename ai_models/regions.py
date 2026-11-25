"""Cloud regions that regional model specs (`AIModelSpec.region`) run in."""

import typing

from daras_ai_v2.custom_enum import GooeyEnum


class RegionData(typing.NamedTuple):
    db_value: str  # what AIModelSpec.region stores
    label: str
    country_code: str | None
    # the broad area the model picker filters on
    geolocation: typing.Literal["eu", "uk", "us", "ap", "sg"]
    # ecocost's grid for the CO2e estimate; None uses ecocost's default
    eco_grid: str | None


GEOLOCATION_LABELS = {
    "eu": "EU",
    "uk": "UK",
    "us": "US",
    "ap": "Asia-Pacific",
    "sg": "Singapore",
}


class Region(RegionData, GooeyEnum):
    # multi-region and country-level, for hosts that don't name a region
    eu = RegionData("eu", "EU", None, "eu", None)
    uk = RegionData("uk", "UK", "GB", "uk", "GB")
    us = RegionData("us", "US", "US", "us", "US")
    sg = RegionData("sg", "Singapore", "SG", "sg", "SG")
    # AWS
    eu_central_1 = RegionData("eu-central-1", "EU · Frankfurt", "DE", "eu", "DE")
    eu_north_1 = RegionData("eu-north-1", "EU · Stockholm", "SE", "eu", None)
    eu_south_1 = RegionData("eu-south-1", "EU · Milan", "IT", "eu", None)
    eu_west_1 = RegionData("eu-west-1", "EU · Ireland", "IE", "eu", None)
    eu_west_3 = RegionData("eu-west-3", "EU · Paris", "FR", "eu", "FR")
    eu_west_2 = RegionData("eu-west-2", "UK · London", "GB", "uk", "GB")
    us_east_1 = RegionData("us-east-1", "US · Virginia", "US", "us", "US-VA")
    us_east_2 = RegionData("us-east-2", "US · Ohio", "US", "us", "US-OHV")
    us_west_2 = RegionData("us-west-2", "US · Oregon", "US", "us", "US-NW")
    ap_northeast_1 = RegionData("ap-northeast-1", "Tokyo", "JP", "ap", None)
    ap_northeast_3 = RegionData("ap-northeast-3", "Osaka", "JP", "ap", None)
    ap_south_1 = RegionData("ap-south-1", "Mumbai", "IN", "ap", "IN")
    ap_southeast_2 = RegionData("ap-southeast-2", "Sydney", "AU", "ap", None)
    # Google Cloud
    europe_central2 = RegionData("europe-central2", "EU · Warsaw", "PL", "eu", None)
    europe_north1 = RegionData("europe-north1", "EU · Finland", "FI", "eu", None)
    europe_southwest1 = RegionData("europe-southwest1", "EU · Madrid", "ES", "eu", None)
    europe_west1 = RegionData("europe-west1", "EU · Belgium", "BE", "eu", None)
    europe_west4 = RegionData("europe-west4", "EU · Netherlands", "NL", "eu", None)
    europe_west8 = RegionData("europe-west8", "EU · Milan", "IT", "eu", None)
    us_central1 = RegionData("us-central1", "US · Iowa", "US", "us", "US-MIDW")
    us_east1 = RegionData("us-east1", "US · South Carolina", "US", "us", "US-SE")
    us_east4 = RegionData("us-east4", "US · Virginia", "US", "us", "US-VA")
    us_east5 = RegionData("us-east5", "US · Ohio", "US", "us", "US-OHV")
    us_south1 = RegionData("us-south1", "US · Dallas", "US", "us", "US-TX")
    us_west1 = RegionData("us-west1", "US · Oregon", "US", "us", "US-NW")
    us_west4 = RegionData("us-west4", "US · Las Vegas", "US", "us", "US-SW")
    asia_northeast1 = RegionData("asia-northeast1", "Tokyo", "JP", "ap", None)
    # Azure
    francecentral = RegionData("francecentral", "EU · Paris", "FR", "eu", "FR")
    germanywestcentral = RegionData(
        "germanywestcentral", "EU · Frankfurt", "DE", "eu", "DE"
    )
    polandcentral = RegionData("polandcentral", "EU · Warsaw", "PL", "eu", None)
    swedencentral = RegionData("swedencentral", "EU · Sweden", "SE", "eu", None)
    westeurope = RegionData("westeurope", "EU · Netherlands", "NL", "eu", None)
    eastus = RegionData("eastus", "US · Virginia", "US", "us", "US-VA")
    eastus2 = RegionData("eastus2", "US · Virginia", "US", "us", "US-VA")
    westus3 = RegionData("westus3", "US · Arizona", "US", "us", "US-SW")
    japaneast = RegionData("japaneast", "Tokyo", "JP", "ap", None)
    koreacentral = RegionData("koreacentral", "Seoul", "KR", "ap", None)

    @classmethod
    def get_by_db_value(cls, db_value: str) -> "Region | None":
        try:
            return cls.from_db(db_value)
        except ValueError:
            return None


def region_label(region: str) -> str:
    """ "EU · Frankfurt" for a known region, the raw value for an unknown one, "Global" for none."""
    if not region:
        return "Global"
    info = Region.get_by_db_value(region)
    return info.label if info else region
