from ariadne import (gql, make_executable_schema, ObjectType)
from sqlalchemy import func
from ariadne.asgi import GraphQL
from starlette.middleware.cors import CORSMiddleware
import datetime as dt
from sqlalchemy import Column, Integer, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import create_engine

ModelBase = declarative_base()

class Project(ModelBase):
    __tablename__ = 'project'

    id = Column(Integer, primary_key=True)
    name = Column(Text, unique=True)

    pomodoros = relationship("Pomodoro", back_populates="project")

    def __str__(self):
        return f"{self.name}"


class Pomodoro(ModelBase):
    __tablename__ = 'pomodoro'

    id = Column(Integer, primary_key=True)
    description_id = Column(Integer, ForeignKey('project.id'))
    duration = Column(Integer)
    start = Column(Integer, default=lambda: dt.datetime.utcnow().timestamp())

    # Establish the relationship to project
    project = relationship("Project", back_populates="pomodoros")

    def __str__(self):
        return f"{self.id}"


type_defs = gql(
    """
    type Query {
        pomodoro(id : Int!): Pomodoro
        project(project: String!, start_time: Int, end_time: Int): Project!
        work(start_time: Int, end_time: Int): [Project!]!
        projects(start_time: Int, end_time: Int): [Project!]!
    }

    type Mutation {
        pomodoro (duration: Int!, project: String!): Pomodoro!
    }

    type Pomodoro {
        id: Int!
        duration: Int!
        start: Int!
    }

    type Project {
        id: Int!
        name: String!
        total_duration: Int!
        n_pomodoros: Int!
        pomodoros: [Pomodoro!]!
        as_of: String!
        last_touched: String!
    }

    """)

engine = create_engine('postgresql://pomo:pomo@localhost:5432/pomo')

ModelBase.metadata.create_all(engine)

Session = sessionmaker(bind=engine)

query = ObjectType("Query")
mutation = ObjectType("Mutation")
pomodoro = ObjectType("Pomodoro")
project = ObjectType("Project")

@query.field("pomodoro")
def resolve_pomodoro(obj, info, id):

    session = Session()

    # if id is a Pomodoro
    if id.__class__ == Pomodoro:
        pomo_obj = id
    else:
        pomo_obj = session.query(Pomodoro).filter_by(id=id).first()

    if not pomo_obj:
        return None

    return {'id': pomo_obj.id, 'duration': pomo_obj.duration, 'start':
            pomo_obj.start}

@mutation.field("pomodoro")
def mutate_pomodoro(obj, info, duration, project):

    session = Session()

    # standardize project name
    project = (project
               .lower()
               .replace(" ", "_")
               .replace(".", "-"))

    # look up project by name, create if doesn't exist
    project_obj = session.query(Project).filter_by(name=project).first()

    if not project_obj:
        project_obj = Project(name=project)

    start_timestamp = int((dt.datetime.utcnow() -
        dt.timedelta(seconds=duration)).timestamp())
    pomo = Pomodoro(duration=duration, start=start_timestamp)
    pomo.project = project_obj

    try:
        session.add(pomo)
        session.commit()
        session.refresh(pomo)
        pomo_details = {'id': pomo.id, 'duration': pomo.duration, 'start': pomo.start}
    except Exception as e:
        session.rollback()  # Rollback the transaction in case of an exception
        raise e
    finally:
        session.close()  # Close the session to cleanup the resources

    return pomo_details

@query.field("projects")
def resolve_projects(obj, info, start_time=None, end_time=None):
    """
    Return list of projects
    """
    session = Session()
    return [resolve_project(obj, info, x, start_time, end_time) for x in
        session.query(Project).all()]

@query.field("project")
def resolve_project(obj, info, project, start_time=None, end_time=None):

    # look up project by name, create if doesn't exist
    session = Session()

    # if project is a Project
    if project.__class__ == Project:
        project_obj = project
    else:
        project_obj = session.query(Project).filter_by(name=project).first()

    if not project_obj:
        return None

    conditions = [Pomodoro.project == project_obj]

    # If start_time is provided, parse it and add to conditions
    if start_time:
        conditions.append(Pomodoro.start >= start_time)

    # If end_time is provided, parse it and add to conditions
    if end_time:
        conditions.append(Pomodoro.start <= end_time)

    # Calculate total duration and count of pomodoros directly in the database
    total_duration, npomo = session.query(
        func.sum(Pomodoro.duration), func.count(Pomodoro.id)
    ).filter(*conditions).first()

    pomodoros = [resolve_pomodoro(obj, info, x) for x in project_obj.pomodoros][::-1]

    return {'id': project_obj.id, 'name': project_obj.name, 'total_duration':
            total_duration or 0, 'n_pomodoros': npomo, 'pomodoros':
            pomodoros, 'as_of': str(int(time.time()*1000)), 'last_touched': str(pomodoros[0]['start']*1000)}

@query.field("work")
def resolve_work(obj, info, start_time=None, end_time=None):
    session = Session()

    # Parse the start and end times if provided
    conditions = []
    if start_time:
        conditions.append(Pomodoro.start >= start_time)
    if end_time:
        conditions.append(Pomodoro.start <= end_time)

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
        resolve_project(obj, info, project=project.name, start_time=start_time,
                        end_time=end_time)
        for project in projects_within_time_range
    ]

    return work_data


schema = make_executable_schema(type_defs, query, mutation, pomodoro, project)

app = CORSMiddleware(GraphQL(schema, debug=True), allow_origins=['*'],
                     allow_methods=['*'], allow_headers=['*'])


