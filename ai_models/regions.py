"""Cloud regions that regional model specs (`AIModelSpec.region`) run in."""

import typing


class Region(typing.NamedTuple):
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

REGIONS: dict[str, Region] = {
    # multi-region and country-level, for hosts that don't name a region
    "eu": Region("EU", None, "eu", None),
    "uk": Region("UK", "GB", "uk", "GB"),
    "us": Region("US", "US", "us", "US"),
    "sg": Region("Singapore", "SG", "sg", "SG"),
    # AWS
    "eu-central-1": Region("EU · Frankfurt", "DE", "eu", "DE"),
    "eu-north-1": Region("EU · Stockholm", "SE", "eu", None),
    "eu-south-1": Region("EU · Milan", "IT", "eu", None),
    "eu-west-1": Region("EU · Ireland", "IE", "eu", None),
    "eu-west-3": Region("EU · Paris", "FR", "eu", "FR"),
    "eu-west-2": Region("UK · London", "GB", "uk", "GB"),
    "us-east-1": Region("US · Virginia", "US", "us", "US-VA"),
    "us-east-2": Region("US · Ohio", "US", "us", "US-OHV"),
    "us-west-2": Region("US · Oregon", "US", "us", "US-NW"),
    "ap-northeast-1": Region("Tokyo", "JP", "ap", None),
    "ap-northeast-3": Region("Osaka", "JP", "ap", None),
    "ap-south-1": Region("Mumbai", "IN", "ap", "IN"),
    "ap-southeast-2": Region("Sydney", "AU", "ap", None),
    # Google Cloud
    "europe-central2": Region("EU · Warsaw", "PL", "eu", None),
    "europe-north1": Region("EU · Finland", "FI", "eu", None),
    "europe-southwest1": Region("EU · Madrid", "ES", "eu", None),
    "europe-west1": Region("EU · Belgium", "BE", "eu", None),
    "europe-west4": Region("EU · Netherlands", "NL", "eu", None),
    "europe-west8": Region("EU · Milan", "IT", "eu", None),
    "us-central1": Region("US · Iowa", "US", "us", "US-MIDW"),
    "us-east1": Region("US · South Carolina", "US", "us", "US-SE"),
    "us-east4": Region("US · Virginia", "US", "us", "US-VA"),
    "us-east5": Region("US · Ohio", "US", "us", "US-OHV"),
    "us-south1": Region("US · Dallas", "US", "us", "US-TX"),
    "us-west1": Region("US · Oregon", "US", "us", "US-NW"),
    "us-west4": Region("US · Las Vegas", "US", "us", "US-SW"),
    "asia-northeast1": Region("Tokyo", "JP", "ap", None),
    # Azure
    "francecentral": Region("EU · Paris", "FR", "eu", "FR"),
    "germanywestcentral": Region("EU · Frankfurt", "DE", "eu", "DE"),
    "polandcentral": Region("EU · Warsaw", "PL", "eu", None),
    "swedencentral": Region("EU · Sweden", "SE", "eu", None),
    "westeurope": Region("EU · Netherlands", "NL", "eu", None),
    "eastus": Region("US · Virginia", "US", "us", "US-VA"),
    "eastus2": Region("US · Virginia", "US", "us", "US-VA"),
    "westus3": Region("US · Arizona", "US", "us", "US-SW"),
    "japaneast": Region("Tokyo", "JP", "ap", None),
    "koreacentral": Region("Seoul", "KR", "ap", None),
}


def region_label(region: str) -> str:
    """ "EU · Frankfurt" for a known region, the raw value for an unknown one, "Global" for none."""
    if not region:
        return "Global"
    info = REGIONS.get(region)
    return info.label if info else region
