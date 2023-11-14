from ariadne import (gql, make_executable_schema, ObjectType)
from sqlalchemy import func
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
        project(project: String!, start_time: String, end_time: String): Work
    }

    type Mutation {
        pomodoro (duration: Int!, project: String!): Pomodoro!
    }

    type Pomodoro {
        id: Int!
        duration: Int!
    }

    type Work {
        total_duration: Int!
        npomo: Int!
    }

    """)

engine = create_engine('sqlite:///pomodoro.db')

Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

session = Session()

query = ObjectType("Query")
mutation = ObjectType("Mutation")
pomodoro = ObjectType("Pomodoro")
work = ObjectType("Work")

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

@query.field("project")
def resolve_project(obj, info, project, start_time=None, end_time=None):

    # look up project by name, create if doesn't exist

    project_obj = session.query(Project).filter_by(name=project).first()

    if not project_obj:
        return None

    conditions = [Pomodoro.project == project_obj]

    # If start_time is provided, parse it and add to conditions
    if start_time:
        start_time = dt.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S')
        conditions.append(Pomodoro.start >= start_time)

    # If end_time is provided, parse it and add to conditions
    if end_time:
        end_time = dt.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S')
        conditions.append(Pomodoro.start <= end_time)

    # Calculate total duration and count of pomodoros directly in the database
    total_duration, npomo = session.query(
        func.sum(Pomodoro.duration), func.count(Pomodoro.id)
    ).filter(*conditions).first()

    return {'total_duration': total_duration or 0, 'npomo': npomo}

schema = make_executable_schema(type_defs, query, mutation, pomodoro, work)

app = CORSMiddleware(GraphQL(schema, debug=True), allow_origins=['*'],
                     allow_methods=['*'], allow_headers=['*'])


