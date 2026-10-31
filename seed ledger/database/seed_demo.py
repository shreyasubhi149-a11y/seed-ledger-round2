"""Insert fictional demo records into an empty database."""

from datetime import datetime, timedelta, timezone

from backend.auth import hash_password
from database.connection import initialize, SessionLocal
from database import models as m


def seed():
    initialize()

    with SessionLocal() as db:
        if db.query(m.Grower).count():
            print(
                "Database already has growers. "
                "Existing records were left unchanged."
            )
            return

        profiles = [
            (
                "Asha Patil",
                "asha@example.com",
                "Bengaluru, Karnataka",
                "Saves vegetable varieties and records test results.",
            ),
            (
                "Ravi Kumar",
                "ravi@example.com",
                "Mysuru, Karnataka",
                "Kitchen gardener maintaining traditional seeds.",
            ),
            (
                "Meera Rao",
                "meera@example.com",
                "Udupi, Karnataka",
                "Maintains a small brinjal collection.",
            ),
            (
                "Farhan Ali",
                "farhan@example.com",
                "Bengaluru, Karnataka",
                "Grows greens and legumes with a seed circle.",
            ),
            (
                "Lakshmi Nair",
                "lakshmi@example.com",
                "Kochi, Kerala",
                "Preserves family seed histories.",
            ),
        ]

        growers = []

        for name, email, location, bio in profiles:
            grower = m.Grower(
                name=name,
                email=email,
                location=location,
                bio=bio,
            )

            db.add(grower)
            db.flush()

            growers.append(grower)

            db.add(
                m.Account(
                    grower_id=grower.id,
                    email=email,
                    password_hash=hash_password(
                        "SeedDemo2026!"
                    ),
                )
            )

        # owner index, variety, species, stock,
        # germination percentage, generation, age in days
        specifications = [
            (
                0,
                "Arka Vikas Tomato",
                "Solanum lycopersicum",
                240,
                92,
                1,
                160,
            ),
            (
                1,
                "Arka Vikas Tomato",
                "Solanum lycopersicum",
                120,
                85,
                2,
                40,
            ),
            (
                2,
                "Udupi Brinjal",
                "Solanum melongena",
                180,
                78,
                3,
                100,
            ),
            (
                3,
                "Amaranth Greens",
                "Amaranthus",
                500,
                94,
                1,
                60,
            ),
            (
                4,
                "Cowpea Local",
                "Vigna unguiculata",
                95,
                64,
                2,
                420,
            ),
            (
                0,
                "Ragi Local",
                "Eleusine coracana",
                350,
                None,
                1,
                70,
            ),
            (
                1,
                "Okra Local",
                "Abelmoschus esculentus",
                160,
                88,
                1,
                120,
            ),
            (
                3,
                "Cowpea Local",
                "Vigna unguiculata",
                70,
                82,
                2,
                210,
            ),
        ]

        lots = []
        now = datetime.now(timezone.utc)

        for index, specification in enumerate(specifications):
            (
                owner,
                variety,
                species,
                stock,
                germination,
                generation,
                age,
            ) = specification

            lot = m.SeedLot(
                owner_id=growers[owner].id,
                variety=variety,
                species=species,
                available_seeds=stock,
                is_available=True,
                generation=generation,
                date_saved=now - timedelta(days=age),
                source="Demonstration harvest",
                storage_location="Labelled dry storage box",
                pollination="unknown",
                description=(
                    "Fictional hackathon sample. "
                    "Quality values are demonstration data."
                ),
            )

            if index == 1:
                lot.parent_lot_id = lots[0].id

            db.add(lot)
            db.flush()

            lots.append(lot)

            if germination is not None:
                db.add(
                    m.QualityReport(
                        seed_lot_id=lot.id,
                        reporter_id=growers[owner].id,
                        germination_rate=germination,
                        purity_rating=4,
                        trueness_to_type=4,
                        notes=(
                            "Synthetic observation "
                            "for demonstration."
                        ),
                    )
                )

            db.add(
                m.Activity(
                    actor_id=growers[owner].id,
                    kind="harvest",
                    description=(
                        f"Registered {variety} "
                        "(synthetic sample)"
                    ),
                )
            )

        db.add(
            m.Exchange(
                seed_lot_id=lots[0].id,
                from_grower_id=growers[0].id,
                to_grower_id=growers[1].id,
                quantity="30 seeds",
                exchange_date=now - timedelta(days=100),
                notes=(
                    "Synthetic historical exchange. "
                    "Ravi later grew a new harvest, generation 2."
                ),
            )
        )

        db.add(
            m.SeedRequest(
                seed_lot_id=lots[0].id,
                requester_id=growers[1].id,
                quantity=20,
                message=(
                    "I would like a backup batch "
                    "for our neighbourhood garden."
                ),
                status="pending",
            )
        )

        db.commit()

        print(
            "Created 5 fictional growers, 8 seed lots, "
            "7 observations, 1 historical exchange "
            "and 1 pending request."
        )
        print("Demo email: asha@example.com")
        print("Demo password: SeedDemo2026!")


if __name__ == "__main__":
    seed()