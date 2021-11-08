export interface ICandidate {
  id: string;
  name: string;
  numVotes: string;
}

export interface IContest {
  id: string;
  name: string;
  allowWriteIns?: Boolean;
  totalBallotsCast: string;
  candidates: ICandidate[]
}

export interface IPrecinct {
  id: string;
  name: string;
}

export interface IBallotType {
  id: string;
  name?: string;
}
