from app.clients.usda_fdc.models import (
    BrandedFoodsResponse,
    FoundationFoodsResponse,
)


def test_validates_foundation_foods_and_filters_null_placeholders() -> None:
    payload = {
        "FoundationFoods": [
            {
                "foodClass": "FinalFood",
                "description": "Hummus, commercial",
                "foodNutrients": [
                    {
                        "type": "FoodNutrient",
                        "id": 2219707,
                        "nutrient": {
                            "id": 1120,
                            "number": "334",
                            "name": "Cryptoxanthin, beta",
                            "rank": 7460,
                            "unitName": "µg",
                        },
                        "amount": 3.0,
                    }
                ],
                "foodAttributes": [],
                "foodCategory": {"description": "Legumes and Legume Products"},
                "isHistoricalReference": False,
                "ndbNumber": 16158,
                "dataType": "Foundation",
                "fdcId": 321358,
                "publicationDate": "4/1/2019",
            },
            None,
        ]
    }

    response = FoundationFoodsResponse.model_validate(payload)

    assert len(response.foods) == 1
    assert response.foods[0].fdc_id == 321358
    assert response.foods[0].food_nutrients[0].nutrient.unit_name == "µg"
    assert response.model_dump(by_alias=True)["FoundationFoods"][1] is None


def test_validates_branded_foods() -> None:
    payload = {
        "BrandedFoods": [
            {
                "foodClass": "Branded",
                "description": "SUPREME BASMATI RICE",
                "foodNutrients": [],
                "foodAttributes": [],
                "modifiedDate": "4/26/2020",
                "availableDate": "4/26/2020",
                "marketCountry": "United States",
                "brandOwner": "VEETEE",
                "dataSource": "LI",
                "brandedFoodCategory": "Rice",
                "gtinUpc": "8906004982514",
                "ingredients": "BASMATI RICE.",
                "servingSize": 45,
                "servingSizeUnit": "g",
                "householdServingFullText": "0.25 cup",
                "labelNutrients": {
                    "calories": {"value": 160},
                    "vitaminD": {"value": 0},
                },
                "tradeChannels": ["NO_TRADE_CHANNEL"],
                "microbes": [],
                "foodUpdateLog": [],
                "dataType": "Branded",
                "fdcId": 1106304,
                "publicationDate": "11/13/2020",
            }
        ]
    }

    response = BrandedFoodsResponse.model_validate(payload)
    food = response.branded_foods[0]

    assert food.fdc_id == 1106304
    assert food.label_nutrients.calories is not None
    assert food.label_nutrients.calories.value == 160
    assert food.label_nutrients.vitamin_d is not None
