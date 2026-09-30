from cms.models import SDG

# Icons: the UN's "E Transparent Inverted Icons" (WEB) set, re-hosted on our bucket.
DEFAULT_SDGS = [
    SDG(
        number=1,
        name="No Poverty",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b1fa86b4-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-01.png",
    ),
    SDG(
        number=2,
        name="Zero Hunger",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b2ad37e6-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-02.png",
    ),
    SDG(
        number=3,
        name="Good Health and Well-being",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b337fc5a-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-03.png",
    ),
    SDG(
        number=4,
        name="Quality Education",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b3bb355c-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-04.png",
    ),
    SDG(
        number=5,
        name="Gender Equality",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b449565c-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-05.png",
    ),
    SDG(
        number=6,
        name="Clean Water and Sanitation",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b4b4004c-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-06.png",
    ),
    SDG(
        number=7,
        name="Affordable and Clean Energy",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b54b4588-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-07.png",
    ),
    SDG(
        number=8,
        name="Decent Work and Economic Growth",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b5cef770-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-08.png",
    ),
    SDG(
        number=9,
        name="Industry, Innovation and Infrastructure",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b650eb68-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-09.png",
    ),
    SDG(
        number=10,
        name="Reduced Inequalities",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b6e3d36a-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-10.png",
    ),
    SDG(
        number=11,
        name="Sustainable Cities and Communities",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b74d56aa-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-11.png",
    ),
    SDG(
        number=12,
        name="Responsible Consumption and Production",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b7ece918-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-12.png",
    ),
    SDG(
        number=13,
        name="Climate Action",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b87a922c-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-13.png",
    ),
    SDG(
        number=14,
        name="Life Below Water",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b905f3a8-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-14.png",
    ),
    SDG(
        number=15,
        name="Life on Land",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/b99b51f0-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-15.png",
    ),
    SDG(
        number=16,
        name="Peace, Justice and Strong Institutions",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/ba087d8e-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-16.png",
    ),
    SDG(
        number=17,
        name="Partnerships for the Goals",
        icon_url="https://storage.googleapis.com/dara-c1b52.appspot.com/daras_ai/media/baa4cd24-bca9-11f1-8b4f-8a14a92e48b6/sdg-icon-17.png",
    ),
]


def run():
    # Keyed on `number`: existing rows, and any admin edits to them, are left alone.
    SDG.objects.bulk_create(DEFAULT_SDGS, ignore_conflicts=True)
