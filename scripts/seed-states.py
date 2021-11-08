# pylint: disable=invalid-name
import json
from os import path

import uuid
from server.database import db_session
from server.models import State, Jurisdiction

if __name__ == "__main__":
    # Opening JSON file state and jurisdictions data
    with open(path.join(path.dirname(path.abspath(__file__)), 'state_info.json'), encoding='utf-8') as file:
        # reading from json dictionary
        data = json.load(file)
        for state_obj in data['states']:
            state = State(id=str(uuid.uuid4()), name=state_obj["name"])
            db_session.add(state)
            if "jurisdictions" in state_obj:
                print("Adding jurisdictions for state "+state.name+": 🤞")
                for jurisdiction_item in state_obj["jurisdictions"]:
                    jurisdiction = Jurisdiction(id=str(uuid.uuid4()), name=jurisdiction_item, state_id=state.id)
                    db_session.add(jurisdiction)

    # commit to DB
    db_session.commit()
    print("States & Jurisdictions seeded successfully 👍")
