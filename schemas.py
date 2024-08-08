from pydantic import BaseModel

class PlayerBase(BaseModel):
    name: str
    team: str
    position: str
    price: int

class PlayerCreate(PlayerBase):
    pass

class Player(PlayerBase):
    id: int
    
    class Config:
        orm_mode= True