import argparse

from .matchup_evaluation import evaluate_matchups
from .nba_ingestion import ingest_nba
from .db import Base, SessionLocal, engine
from .evaluation import evaluate_nfl_baseline
from .real_ingestion import ingest_nba_roster, ingest_nfl


def main() -> None:
    parser = argparse.ArgumentParser(description="MatchupEdge data operations")
    subparsers = parser.add_subparsers(dest="command", required=True)
    ingest = subparsers.add_parser("ingest-nfl", help="Load real NFL schedules, rosters, stats, and baseline projections")
    ingest.add_argument("--seasons", nargs="+", type=int)
    ingest.add_argument("--cache-dir", default="data/cache/nflverse")
    subparsers.add_parser("ingest-nba-roster", help="Load the real active NBA player and team static datasets")
    subparsers.add_parser("evaluate-nfl", help="Evaluate chronological NFL recency baselines")
    subparsers.add_parser("ingest-nba", help="Load NBA schedule, season roster and game logs")
    subparsers.add_parser("evaluate-matchups", help="Chronological validation and opponent sensitivity report")
    args = parser.parse_args()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        if args.command == "ingest-nfl":
            print(ingest_nfl(session, cache_dir=args.cache_dir, seasons=args.seasons))
        elif args.command == "ingest-nba-roster":
            print(ingest_nba_roster(session))
        elif args.command == "ingest-nba":
            print(ingest_nba(session))
        elif args.command == "evaluate-matchups":
            print(evaluate_matchups(session))
        elif args.command == "evaluate-nfl":
            print(evaluate_nfl_baseline(session))


if __name__ == "__main__":
    main()
