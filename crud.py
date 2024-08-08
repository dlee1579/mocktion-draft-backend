from sqlalchemy.orm import Session

import models, schemas

def get_player(db: Session, player_id: int):
    return db.query(models.Player).filter(models.Player.id == player_id).first()

def create_player(db: Session, player: schemas.PlayerCreate):
    db_player = models.Player(name=player.name, team=player.team, position=player.position)
    db.add(db_player)
    db.commit()
    db.refresh(db_player)
    return db_player

def get_players(db: Session):
    return db.query(models.Player).all()
