from sqlalchemy.orm import Session
from sqlalchemy import exists
from app.models.survey import Survey
from app.models import User


def customer_exists(db: Session, customer_id: int) -> bool:
    return bool(db.query(exists().where(User.id == customer_id)).scalar())


def survey_exists_by_user(db: Session, customer_id: int) -> bool:
    return bool(db.query(exists().where(Survey.customer_id == customer_id)).scalar())


def create_survey(db: Session, survey_obj: Survey) -> Survey:
    db.add(survey_obj)
    return survey_obj
