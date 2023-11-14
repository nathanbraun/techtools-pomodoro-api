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
        project(project: String!, start_time: String, end_time: String): Project
        work(start_time: String, end_time: String): [Project!]!
    }

    type Mutation {
        pomodoro (duration: Int!, project: String!): Pomodoro!
    }

    type Pomodoro {
        id: Int!
        duration: Int!
    }

    type Project {
        id: Int!
        name: String!
        total_duration: Int!
        n_pomodoros: Int!
    }

    """)

engine = create_engine('sqlite:///pomodoro.db')

Base.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

session = Session()

query = ObjectType("Query")
mutation = ObjectType("Mutation")
pomodoro = ObjectType("Pomodoro")
project = ObjectType("Project")

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

    return {'id': project_obj.id, 'name': project_obj.name, 'total_duration':
            total_duration or 0, 'n_pomodoros': npomo}

@query.field("work")
def resolve_work(obj, info, start_time=None, end_time=None):
    # Parse the start and end times if provided
    conditions = []
    if start_time:
        start_time_dt = dt.datetime.strptime(start_time, '%Y-%m-%dT%H:%M:%S')
        conditions.append(Pomodoro.start >= start_time_dt)
    if end_time:
        end_time_dt = dt.datetime.strptime(end_time, '%Y-%m-%dT%H:%M:%S')
        conditions.append(Pomodoro.start <= end_time_dt)

    # Query the Pomodoro table to find all pomodoros within the time range
    # and get the distinct associated projects
    projects_within_time_range = (
        session.query(Project)
        .join(Pomodoro, Pomodoro.description_id == Project.id)
        .filter(*conditions)
        .distinct()
    ).all()

    # Use resolve_project to get details for each project
    work_data = [
        resolve_project(obj, info, project=project.name, start_time=start_time, end_time=end_time)
        for project in projects_within_time_range
    ]

    return work_data

schema = make_executable_schema(type_defs, query, mutation, pomodoro, project)

app = CORSMiddleware(GraphQL(schema, debug=True), allow_origins=['*'],
                     allow_methods=['*'], allow_headers=['*'])


