"""
## Play Texas Hold'em Poker with Airflow

This DAG will draw cards for two players (and also shows how to use a teardown task 
to clean up XComs after the DAG has finished running).
"""

from airflow.decorators import dag, task
from pendulum import datetime
from airflow.providers.amazon.aws.operators.s3 import S3DeleteObjectsOperator
from airflow.providers.http.operators.http import SimpleHttpOperator
from airflow.models.baseoperator import chain
import os
import json
import requests


def draw_cards(deck_id, number):
    cards = []
    for i in range(number):
        r = requests.get(f"https://deckofcardsapi.com/api/deck/{deck_id}/draw/?count=1")
        cards.append(r.json()["cards"][0])
    return cards


@dag(
    start_date=datetime(2023, 8, 1),
    schedule=None,
    catchup=False,
    render_template_as_native_obj=True,
    tags=[".as_teardown()", "setup/teardown"],
)
def setup_teardown_cleanup_xcom():
    shuffle_cards = SimpleHttpOperator(
        task_id="shuffle_cards",
        method="GET",
        http_conn_id="http_default",
        deferrable=True,
    )

    @task
    def player_one_draws_cards(shuffle_response):
        deck_id = json.loads(shuffle_response)["deck_id"]
        cards = draw_cards(deck_id, 2)
        return cards

    @task
    def player_two_draws_cards(shuffle_response):
        deck_id = json.loads(shuffle_response)["deck_id"]
        cards = draw_cards(deck_id, 2)
        return cards

    @task
    def cards_on_the_table(shuffle_response):
        deck_id = json.loads(shuffle_response)["deck_id"]
        cards = draw_cards(deck_id, 5)
        return cards

    @task
    def evaluate_cards(player_one_cards, player_two_cards, cards_on_the_table):
        for card in player_one_cards:
            print(f"Player 1 drew: {card['value']} of {card['suit']}")
        for card in player_two_cards:
            print(f"Player 2 drew: {card['value']} of {card['suit']}")
        for card in cards_on_the_table:
            print(f"On the table we have a: {card['value']} of {card['suit']}")

    clean_up_xcom = S3DeleteObjectsOperator(
        task_id="clean_up_xcom",
        bucket=os.environ["XCOM_BACKEND_BUCKET_NAME"],
        prefix="{{ run_id }}/",
        aws_conn_id=os.environ["XCOM_BACKEND_AWS_CONN_ID"],
    )

    # set dependencies
    cards_player_1 = player_one_draws_cards(shuffle_cards.output)
    cards_player_2 = player_two_draws_cards(shuffle_cards.output)
    cards_on_table = cards_on_the_table(shuffle_cards.output)

    cards_player_1 >> cards_player_2 >> cards_on_table

    (
        evaluate_cards(cards_player_1, cards_player_2, cards_on_table) >> clean_up_xcom
    ).as_teardown(
        setups=[shuffle_cards, cards_player_1, cards_player_2, cards_on_table]
    )


setup_teardown_cleanup_xcom()
