from fastapi import FastAPI, Depends
import requests
import json
import pandas as pd
import math

import models, crud, schemas
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from constants import team_id_name_map, position_id_map

models.Base.metadata.create_all(bind=engine)

app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/")
def root():
    return {"message": "Hello World"}

@app.get('/draft/{draft_id}')
def get_draft_picks(draft_id):
    url = "https://api.sleeper.app/v1/draft/{}/picks".format(draft_id)
    response = requests.get(url)
    draft_picks = json.loads(response.content)
    
    return generate_auction_prices_from_sleeper_draft(draft_picks)

@app.get('/fantasypros')
def get_fantasy_pros_auction_values(scoring, num_teams, budget):
    return get_auction_values_from_fantasypros(scoring, num_teams, budget)

@app.get('/auction')
def get_auction_values_using_sleeper_draft_id(draft_id):
    auction_values = get_auction_values_from_fantasypros()
    url = "https://api.sleeper.app/v1/draft/{}/picks".format(draft_id)
    response = requests.get(url)
    draft_picks = json.loads(response.content)
    
    new_prices = generate_auction_prices_from_sleeper_draft(draft_picks)
    
    for i in range(len(auction_values)):
        if i < len(new_prices):
            auction_values[i]["Price"] = new_prices[i]
        else:
            auction_values[i]["Price"] = 1
        auction_values[i]["Value"] = "${}".format(auction_values[i]["Price"])
    return auction_values
    


def generate_auction_prices_from_sleeper_draft(draft_picks):
    # draft picks are in the format of sleeper API response
    auction_prices = []
    for pick in draft_picks:
        auction_prices.append(int(pick.get('metadata').get('amount')))
    auction_prices.sort(reverse=True)
    return auction_prices

def get_auction_values_from_fantasypros(scoring="HALF", num_teams=14, budget=200):
    url = "https://draftwizard.fantasypros.com/auction/fp_nfl.jsp?scoring={}&teams={}&tb={}".format(scoring, num_teams, budget)
    dfs = pd.read_html(url)
    df = dfs[0]
    df.drop("#", axis=1, inplace=True)

    # df['Price'] = df['Unnamed: 3'].apply(lambda x: max(x, 0))
    df['Price'] = df.Value.apply(lambda x: int(x[1:]))
    df.drop("Unnamed: 3", axis=1, inplace=True)
    df['Name'] = df.Overall.apply(lambda x: x[:x.index(" (")])
    df["Team"] = df.Overall.apply(lambda x: x[x.index(" (")+2:x.index(" - ")])
    df["Position"] = df.Overall.apply(lambda x: x[x.index(" - ")+3:x.index(")")])
    df.index.name = "id"
    df.reset_index(inplace=True,)
    df.sort_values("Price",ascending=False, inplace=True)
    return json.loads(df.to_json(orient='records'))

@app.get("/players/", response_model=list[schemas.Player])
def list_players(db: Session = Depends(get_db)):
    players = crud.get_players(db)
    return players

@app.post("/players/", response_model=schemas.Player)
def create_player(player: schemas.PlayerCreate, db: Session = Depends(get_db)):
    return crud.create_player(db=db, player=player)

@app.get('/auction/nfl-com')
def get_auction_values_from_nfl_com(response_model=list[schemas.Player]):
    def parse_player_name_from_overall(overall: str):
        keyword = " - "
        return overall[:overall.find(parse_position_from_overall(overall))].strip()

    def parse_position_from_overall(overall: str):
        positions = ["QB", "RB", "WR", "TE", "K", "DEF", "DL", "LB", "DB"]
        return [position for position in positions if position in overall][0]

    def parse_team_from_overall(overall: str):
        keyword = " - "
        remove_words = ["View News", " Q"]
        overall = overall[overall.find(keyword)+len(keyword):]
        for word in remove_words:
            overall = overall.replace(word, "")
        return overall.strip()
    
    def format_price(price):
        if isinstance(price, int):
            return price
        elif price == "--":
            return 1
        else:
            return int(price)
            

    frames = []
    urls = [
        "https://fantasy.nfl.com/research/rankings",
        "https://fantasy.nfl.com/research/rankings?offset=101"
    ]
    for url in urls:
        df = pd.read_html(url)[0]
        df['position'] = df.Player.apply(parse_position_from_overall)
        df["team"] = df.Player.apply(parse_team_from_overall)
        df["name"] = df.Player.apply(parse_player_name_from_overall)
        # df.reset_index(inplace=True)
        df = df[~df.Bye.isnull()]
        df.rename(columns={"Salary ($)": "price", "index": "id"}, inplace=True)
        df.price = df.price.apply(format_price)
        df.drop(columns=["Rank", "Player", "Bye", "Stock"], inplace=True)
        df = df[~df.position.isin(["DL", "LB", "DB"])]
        frames.append(df)
    master = pd.concat(frames)
    master.reset_index(inplace=True,drop=True)
    master.reset_index(inplace=True)
    master.rename(columns={"index": "id"}, inplace=True)
    return [schemas.Player(**player) for player in master.to_dict(orient='records')]

@app.get('/auction/espn')
def get_auction_values_from_espn(response_model=list[schemas.Player]):
    url = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/2024/segments/0/leaguedefaults/3?view=kona_player_info"
    headers = {
        "sec-ch-ua": "\"Not)A;Brand\";v=\"99\", \"Google Chrome\";v=\"127\", \"Chromium\";v=\"127\"",
        "X-Fantasy-Source": "kona",
        "sec-ch-ua-mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
        "X-Fantasy-Filter": "{\"players\":{\"filterSlotIds\":{\"value\":[0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,23,24]},\"sortAdp\":{\"sortPriority\":2,\"sortAsc\":true},\"sortDraftRanks\":{\"sortPriority\":100,\"sortAsc\":true,\"value\":\"STANDARD\"},\"limit\":200,\"filterRanksForSlotIds\":{\"value\":[0,2,4,6,17,16,8,9,10,12,13,24,11,14,15]},\"filterStatsForTopScoringPeriodIds\":{\"value\":2,\"additionalValue\":[\"002024\",\"102024\",\"002023\",\"022024\"]}}}",
        "Accept": "application/json",
        "Referer": "https://fantasy.espn.com/",
        "X-Fantasy-Platform": "kona-PROD-b9d64b8bc091127981cf8d0e333c0c7283dbaac3",
        "sec-ch-ua-platform": "\"macOS\""
    }

    response = requests.get(url, headers=headers)
    data = response.json()
    player_data = data.get("players")
    return [
        schemas.Player(id=i,
            name=player.get('player').get('fullName'),
            team=team_id_name_map[player.get("player").get("proTeamId")],
            position=position_id_map[player.get("player").get("defaultPositionId")],
            price=int(math.ceil(player.get("player").get("ownership").get("auctionValueAverage"))),
        ) for i, player in enumerate(player_data)
    ]
 
@app.get("/auction/yahoo")
def get_auction_values_from_yahoo(response_model=list[schemas.Player]):
    url = "https://pub-api-ro.fantasysports.yahoo.com/fantasy/v2/league/449.l.public;out=settings/players;position=ALL;start=0;count=200;sort=rank_season;search=;out=auction_values,ranks;ranks=season;ranks_by_position=season;out=expert_ranks;expert_ranks.rank_type=projected_season_remaining/draft_analysis;cut_types=diamond;slices=last7days?format=json_f"
    response = requests.get(url)
    data = response.json()
    player_data = data.get('fantasy_content').get('league').get('players')
    
    return [
        schemas.Player(
            id=i,
            name=player.get('player').get('name').get('full'),
            team=player.get('player').get('editorial_team_abbr'),
            position=player.get('player').get('primary_position'),
            price=math.ceil(
                float(player.get('player').get('average_auction_cost'))
                if player.get('player').get('average_auction_cost') != '-' else 1
            ),
        ) for i, player in enumerate(player_data)
    ]