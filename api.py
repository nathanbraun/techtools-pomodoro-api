from ariadne import (gql, make_executable_schema, ObjectType)
from ariadne.asgi import GraphQL
from starlette.middleware.cors import CORSMiddleware
import datetime as dt
from sqlalchemy import create_engine, Column, Integer, ForeignKey, Text, DateTime
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

class Project(Base):
    __tablename__ = 'project'

    id = Column(Integer, primary_key=True)
    name = Column(Text, unique=True)

class Pomodoro(Base):
    __tablename__ = 'pomodoro'

    id = Column(Integer, primary_key=True)
    description_id = Column(Integer, ForeignKey('project.id'))
    duration = Column(Integer)
    start = Column(DateTime, default=dt.datetime.utcnow)

    # Establish the relationship to project
    project = relationship("Project")


type_defs = gql(
    """
    type Query {
        pomodoro(id : Int!): Pomodoro
    }

    type Mutation {
        pomodoro (duration: Int!, project: String!): Pomodoro!
    }

    type Pomodoro {
        id: Int!
        duration: Int!
    }
    """)

engine = create_engine('sqlite:///pomodoro.db')

Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

session = Session()

query = ObjectType("Query")
mutation = ObjectType("Mutation")
pomodoro = ObjectType("Pomodoro")

@mutation.field("pomodoro")
def resolve_pomodoro(obj, info, duration, project):

    # look up project by name, create if doesn't exist
    project_obj = session.query(Project).filter_by(name=project).first()

    if not project_obj:
        project_obj = Project(name=project)

    start = dt.datetime.utcnow() - dt.timedelta(seconds=duration)
    pomo = Pomodoro(duration=duration, start=start)
    pomo.project = project_obj

    session.add(pomo)
    session.commit()
    return {'id': pomo.id, 'duration': pomo.duration}

schema = make_executable_schema(type_defs, query, mutation, pomodoro)

app = CORSMiddleware(GraphQL(schema, debug=True), allow_origins=['*'],
                     allow_methods=['*'], allow_headers=['*'])


