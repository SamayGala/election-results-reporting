import uuid
import json
from datetime import datetime, timezone
from flask import jsonify, request
from werkzeug.exceptions import Conflict

from . import api
from .jurisdictions import process_jurisdictions_file
from ..models import *  # pylint: disable=wildcard-import
from ..database import db_session
from ..auth import check_access, UserType, restrict_access

from ..util.jsonschema import JSONDict, validate
from ..util.csv_parse import decode_csv_file
from ..util.json_parse import decode_json_file
from ..util.process_file import process_file

from ..activity_log import (
    CreateElection,
    DeleteElection,
    UploadAndProcessFile,
    activity_base,
    record_activity,
)
from server.api import jurisdictions


ELECTION_SCHEMA = {
    "type": "object",
    "properties": {
        "electionName": {"type": "string"},
        "pollsOpen": {"type": "string", "format": "date-time"},
        "pollsClose": {"type": "string", "format": "date-time"},
        "pollsTimezone": {"type": "string"},
        "certificationDate": {"type": "string", "format": "date-time"},
        "organizationId": {"anyOf": [{"type": "string"}, {"type": "null"}]},
    },
    "required": ["organizationId", "electionName", "pollsOpen", "pollsClose", "pollsTimezone", "certificationDate"],
    "additionalProperties": False,
}


def validate_new_election(election: JSONDict):
    validate(election, ELECTION_SCHEMA)

    if Election.query.filter_by(
        name=election["electionName"], organization_id=election["organizationId"]
    ).first():
        raise Conflict(
            f"An election with name '{election['electionName']}' already exists within your organization"
        )

def process_definitions_file(session, election: Election, file: File) -> None:
    def process():
        definition_json = json.loads(election.definition_file.contents)
        bulk_update_from_definitions(
            session,
            election,
            definition_json,
        )

    process_file(session, file, process)

def bulk_update_from_definitions(session, election: Election, definition_json) -> None:
    """
    Updates the precincts for an election all at once. Requires a SQLAlchemy session to use,
    and uses a nested transaction to ensure the changes made are atomic. Depending on your
    session configuration, you may need to explicitly call `commit()` on the session to flush
    changes to the database.
    """
    with session.begin_nested():
        # find election state
        state = State.query.filter_by(
            name=definition_json['state'].replace("State of", "").strip()
        ).one_or_none()
        # if state is valid then process definition file
        if not state:
            #throw error here or create new jurisdiction based on DB seed & use
            raise Conflict(f"Definitions file error: Invalid State ('{definition_json['state']}')")

        for itr_county in definition_json['counties']:
            jurisdiction = Jurisdiction.query.filter_by(
                name=itr_county["name"].replace("County", "").strip(), state_id=state.id
            ).one_or_none()
            if not jurisdiction:
                #throw error here or create new jurisdiction based on DB seed & use
                raise Conflict(f"Definitions file error: Invalid County ('{itr_county['name']}')")

            election_jurisdiction = ElectionJurisdiction(election_id=election.id, jurisdiction_id=jurisdiction.id)
            session.add(election_jurisdiction)
            # populate precinct table
            for itr_precinct in itr_county['precincts']:
                precinct = Precinct.query.filter_by(
                    name=itr_precinct["name"], jurisdiction_id=jurisdiction.id
                ).one_or_none()
                if not precinct:
                    precinct = Precinct(
                        id=str(uuid.uuid4()),
                        name=itr_precinct['name'],
                        definitions_file_id=itr_precinct['id'],
                        jurisdiction_id=jurisdiction.id
                    )
                    session.add(precinct)

        # populate contest table
        for itr_contest in definition_json['contests']:
            contest = Contest(
                id=str(uuid.uuid4()),
                name=itr_contest['title'],
                type=itr_contest['type'],
                seats=itr_contest['seats'],
                allow_write_ins=itr_contest['allowWriteIns'],
                definitions_file_id=itr_contest['id'],
                election=election
            )
            session.add(contest)
            # populate candidate table
            for itr_candidate in itr_contest['candidates']:
                candidate = Candidate(
                    id=str(uuid.uuid4()),
                    name=itr_candidate['name'],
                    definitions_file_id=itr_candidate['id'],
                    contest=contest
                )
                session.add(candidate)
            # check if write-in is allowed in the contest
            if itr_contest['allowWriteIns']:
                candidate = Candidate(
                    id=str(uuid.uuid4()),
                    name="Write-in",
                    definitions_file_id=len(itr_contest['candidates']),
                    contest=contest
                )
                session.add(candidate)


DEFINITION_FILE_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "state": {"type": "string"},
        "counties": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "name": {"type": "string"},
                    "precincts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                            },
                            "required": ["id", "name"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["id", "name", "precincts"],
                "additionalProperties": False,
            },
        },
        "contests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "title": {"type": "string"},
                    "seats": {"type": "integer"},
                    "allowWriteIns": {"type": "boolean"},
                    "candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "name": {"type": "string"},
                            },
                            "required": ["id", "name"],
                            "additionalProperties": True,
                        },
                    },
                },
                "required": ["id", "type", "title", "seats", "allowWriteIns", "candidates"],
                "additionalProperties": True,
            },
        },
    },
    "required": ["title", "state", "counties", "contests"],
    "additionalProperties": True,
}

@api.route("/election", methods=["POST"])
@restrict_access([UserType.ELECTION_ADMIN])
def create_election():
    required_fields = ["organizationId", "electionName", "pollsOpen", "pollsClose", "pollsTimezone", "certificationDate"]
    election = {field : request.values[field] for field in request.values if field in required_fields}
    validate_new_election(election)
    if "jurisdictions" not in request.files:
        raise Conflict("Missing required file parameter 'participating jurisdictions'")
    if "definition" not in request.files:
        raise Conflict("Missing required file parameter 'election definition'")

    input_dt_format = "%a %b %d %Y %H:%M:%S %Z%z"
    election['pollsOpen'] = datetime.strptime(election['pollsOpen'], input_dt_format).astimezone(tz=timezone.utc)
    election['pollsClose'] = datetime.strptime(election['pollsClose'], input_dt_format).astimezone(tz=timezone.utc)
    election['certificationDate'] = datetime.strptime(election['certificationDate'], input_dt_format).replace(tzinfo=timezone.utc)
    election = Election(
        id=str(uuid.uuid4()),
        name=election['electionName'],
        polls_open_at=election['pollsOpen'],
        polls_close_at=election['pollsClose'],
        polls_timezone=election['pollsTimezone'],
        certification_date=election['certificationDate'],
        organization_id=election['organizationId']
    )

    jurisdictions_file = request.files['jurisdictions']
    election.jurisdictions_file = File(
        id=str(uuid.uuid4()),
        name=jurisdictions_file.filename,
        contents=decode_csv_file(jurisdictions_file)
    )

    definition_file = request.files['definition']
    election.definition_file = File(
        id=str(uuid.uuid4()),
        name=definition_file.filename,
        contents=decode_json_file(definition_file, DEFINITION_FILE_SCHEMA)
    )

    check_access([UserType.ELECTION_ADMIN], election)

    db_session.add(election)
    db_session.flush()  # Ensure we can read election.organization in activity_base
    record_activity(
        CreateElection(timestamp=election.created_at, base=activity_base(election))
    )

    process_definitions_file(db_session, election, election.definition_file)
    record_activity(
        UploadAndProcessFile(timestamp=election.definition_file.processing_started_at, base=activity_base(election), file_type="election_definition", error=election.definition_file.processing_error)
    )
    db_session.flush()  # Ensure we can read ElectionJurisdiction data

    process_jurisdictions_file(db_session, election, election.jurisdictions_file)
    record_activity(
        UploadAndProcessFile(timestamp=election.jurisdictions_file.processing_started_at, base=activity_base(election), file_type="jurisdictions", error=election.jurisdictions_file.processing_error)
    )

    db_session.commit()
    return jsonify(status="ok", electionId=election.id)

@api.route("/election/<election_id>", methods=["DELETE"])
@restrict_access([UserType.ELECTION_ADMIN])
def delete_election(election: Election):
    election.deleted_at = datetime.now(timezone.utc)
    record_activity(
        DeleteElection(timestamp=election.deleted_at, base=activity_base(election))
    )
    db_session.commit()
    return jsonify(status="ok")


@api.route("/election/<election_id>/jurisdiction/<jurisdiction_id>/definitions", methods=["GET"])
@restrict_access([UserType.ELECTION_ADMIN, UserType.JURISDICTION_ADMIN])
def get_definition_file(election: Election, jurisdiction: Jurisdiction):
    contests = []
    precincts = []
    for itr_contest in election.contests:
        contest = { key: itr_contest.__dict__[key] for key in itr_contest.__dict__.keys() & {'id', 'name'} }
        contest['candidates'] = [{key: itr_candidate.__dict__[key] for key in itr_candidate.__dict__.keys() & {'id', 'name'} } for itr_candidate in itr_contest.candidates]
        contests.append(contest)
    for itr_precinct in jurisdiction.precincts:
        record_found = False
        for itr_contest in election.contests:
            if ElectionResult.query.filter_by(precinct_id=itr_precinct.id, candidate_id=itr_contest.candidates[0].id).one_or_none():
                record_found = True
        if not record_found:
            precincts.append({ "id": itr_precinct.id, "name": itr_precinct.name })
    return jsonify(contests=contests, precincts=precincts)


@api.route("/election/<election_id>/data", methods=["GET"])
@restrict_access([UserType.ELECTION_ADMIN])
def get_election_data(election: Election):
    election_results = db_session.query(
        Contest.election_id.label('election_id'),
        Jurisdiction.id.label('jurisdiction_id'),
        Jurisdiction.name.label('Jurisdiction_name'),
        Precinct.id.label('precinct_id'),
        Precinct.name.label('precinct_name'),
        Contest.id.label('contest_id'),
        Contest.name.label('contest_name'),
        Candidate.id.label('candidate_id'),
        Candidate.name.label('candidate_name'),
        ElectionResult.created_at.label('created_at'),
        ElectionResult.source.label('source'),
        ElectionResult.num_votes.label('num_votes')
    ).filter(Contest.election_id == election.id)\
    .join(Candidate, Candidate.contest_id == Contest.id, isouter=True, full=True)\
    .join(ElectionJurisdiction, ElectionJurisdiction.election_id == Contest.election_id, isouter=True, full=True)\
    .join(Jurisdiction, Jurisdiction.id == ElectionJurisdiction.jurisdiction_id, isouter=True, full=True)\
    .join(Precinct, Precinct.jurisdiction_id == Jurisdiction.id, isouter=True, full=True)\
    .join(ElectionResult, and_(ElectionResult.precinct_id == Precinct.id, ElectionResult.candidate_id == Candidate.id))\
    .order_by(Contest.election_id, Jurisdiction.id, Precinct.id, Contest.id, Candidate.name)\
    .all()

    if election_results:
        election_data = []
        temp_result_obj = {}
        iter = 0
        for itr_result in election_results:
            if 'id' in temp_result_obj and temp_result_obj['id'] != itr_result[1]+'/'+itr_result[3]+'/'+str(iter):
                election_data.append(temp_result_obj)
                print(election_data)
                iter += 1
                temp_result_obj = {}
            if 'id' not in temp_result_obj:
                temp_result_obj['id'] = itr_result[1]+'/'+itr_result[3]+'/'+str(iter)
                temp_result_obj['jurisdictionName'] = itr_result[2]
                # Will be File name or Precint name + ballot type
                temp_result_obj['fileName'] = itr_result[4]
                temp_result_obj['createdAt'] = itr_result[9]
                temp_result_obj['source'] = itr_result[10]
                temp_result_obj['contests'] = [
                    {
                        'id': itr_result[5],
                        'name': itr_result[6],
                        'totalBallotsCast': itr_result[11],
                        'candidates': [
                            {
                                'id': itr_result[7],
                                'name': itr_result[8],
                                'numVotes': itr_result[11]
                            }
                        ]
                    }
                ]
            else:
                latest_contest = len(temp_result_obj['contests']) - 1
                if temp_result_obj['contests'][latest_contest]['id'] != itr_result[5]:
                    temp_result_obj['contests'].append({
                        'id': itr_result[5],
                        'name': itr_result[6],
                        'totalBallotsCast': itr_result[11],
                        'candidates': [
                            {
                                'id': itr_result[7],
                                'name': itr_result[8],
                                'numVotes': itr_result[11]
                            }
                        ]
                    })
                else:
                    temp_result_obj['contests'][latest_contest]['candidates'].append({
                        'id': itr_result[7],
                        'name': itr_result[8],
                        'numVotes': itr_result[11],
                    })
                    temp_result_obj['contests'][latest_contest]['totalBallotsCast'] += itr_result[11]
        election_data.append(temp_result_obj)
        print(election_data)
        return jsonify(message="Entries Found", data=election_data)
    return jsonify(message="No entry found!")
