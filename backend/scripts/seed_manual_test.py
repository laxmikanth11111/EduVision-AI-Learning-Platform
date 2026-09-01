import asyncio

from app.models.presentation_collaborator import PresentationCollaborator
from sqlalchemy import select

from app.core.security import hash_password
from app.database.session import async_session_factory
from app.models.content_unit import ContentUnit
from app.models.presentation import Presentation
from app.models.user import User
from shared.constants import (
    CollaboratorRole,
    ContentUnitType,
    PresentationStatus,
    PresentationVisibility,
    UserRole,
)

OWNER_EMAIL = "manualtest.owner@example.com"
COLLAB_EMAIL = "manualtest.collaborator@example.com"
TEST_PASSWORD = "ManualTest2026!"


async def seed():
    async with async_session_factory() as session, session.begin():
        # 1. Owner account (individual user)
        result = await session.execute(select(User).where(User.email == OWNER_EMAIL))
        owner = result.scalar_one_or_none()
        if not owner:
            owner = User(
                email=OWNER_EMAIL,
                password_hash=hash_password(TEST_PASSWORD),
                name="Manual Test Owner",
                role=UserRole.USER.value,
                is_verified=True,
                is_active=True,
            )
            session.add(owner)
            await session.flush()
            print(f"Created owner: {owner.id} ({OWNER_EMAIL})")
        else:
            owner.password_hash = hash_password(TEST_PASSWORD)
            owner.role = UserRole.USER.value
            owner.is_verified = True
            owner.is_active = True
            await session.flush()
            print(f"Updated existing owner: {owner.id}")

        # 2. Collaborator account (second individual user, for sharing)
        result = await session.execute(select(User).where(User.email == COLLAB_EMAIL))
        collaborator = result.scalar_one_or_none()
        if not collaborator:
            collaborator = User(
                email=COLLAB_EMAIL,
                password_hash=hash_password(TEST_PASSWORD),
                name="Manual Test Collaborator",
                role=UserRole.USER.value,
                is_verified=True,
                is_active=True,
            )
            session.add(collaborator)
            await session.flush()
            print(f"Created collaborator: {collaborator.id} ({COLLAB_EMAIL})")
        else:
            collaborator.password_hash = hash_password(TEST_PASSWORD)
            collaborator.role = UserRole.USER.value
            collaborator.is_verified = True
            collaborator.is_active = True
            await session.flush()
            print(f"Updated existing collaborator: {collaborator.id}")

        # 3. Presentation owned by owner
        pres_title = "[Manual Test] Introduction to Machine Learning & Neural Networks"
        result = await session.execute(
            select(Presentation).where(
                Presentation.owner_id == owner.id,
                Presentation.title == pres_title
            )
        )
        presentation = result.scalar_one_or_none()
        if not presentation:
            presentation = Presentation(
                title=pres_title,
                description="A realistic test presentation covering Supervised Learning, Neural Networks, Loss Functions, and Training Dynamics for manual verification.",
                topic="Machine Learning & AI",
                status=PresentationStatus.PUBLISHED.value,
                visibility=PresentationVisibility.PRIVATE.value,
                owner_id=owner.id,
                slide_count=2,
                extraction_status="ready",
            )
            session.add(presentation)
            await session.flush()
            print(f"Created presentation: {presentation.id} (Public ID: {presentation.public_id})")
        else:
            print(f"Using existing presentation: {presentation.id} (Public ID: {presentation.public_id})")

        # 4. Content units for presentation
        result = await session.execute(
            select(ContentUnit).where(ContentUnit.presentation_id == presentation.id)
        )
        units = result.scalars().all()
        if not units:
            unit1 = ContentUnit(
                presentation_id=presentation.id,
                unit_type=ContentUnitType.SLIDE.value,
                position=1,
                title="Slide 1: Supervised Learning Foundations",
                raw_text=(
                    "Supervised learning algorithms infer a mathematical function from labeled training data. "
                    "Given input vector X and target label Y, regression predicts continuous values while classification assigns discrete categories. "
                    "Key evaluation metrics include Mean Squared Error (MSE), Accuracy, Precision, Recall, and F1-Score."
                ),
                meta={"slide_number": 1, "source": "Manual Test Dataset"}
            )
            unit2 = ContentUnit(
                presentation_id=presentation.id,
                unit_type=ContentUnitType.SLIDE.value,
                position=2,
                title="Slide 2: Neural Networks & Backpropagation",
                raw_text=(
                    "Artificial Neural Networks comprise layers of nodes connected by trainable weight parameters and non-linear activation functions such as ReLU, Sigmoid, or GELU. "
                    "Forward propagation computes model outputs, while backpropagation calculates gradient vectors using the chain rule. "
                    "Stochastic Gradient Descent (SGD) and Adam update parameters to minimize empirical risk."
                ),
                meta={"slide_number": 2, "source": "Manual Test Dataset"}
            )
            session.add_all([unit1, unit2])
            await session.flush()
            print(f"Created ContentUnits for presentation {presentation.public_id}")

        # 5. Collaborator (second individual user as EDITOR)
        result = await session.execute(
            select(PresentationCollaborator).where(
                PresentationCollaborator.presentation_id == presentation.id,
                PresentationCollaborator.user_id == collaborator.id,
            )
        )
        collab = result.scalar_one_or_none()
        if not collab:
            collab = PresentationCollaborator(
                presentation_id=presentation.id,
                user_id=collaborator.id,
                role=CollaboratorRole.EDITOR.value,
            )
            session.add(collab)
            await session.flush()
            print(f"Added {COLLAB_EMAIL} as EDITOR collaborator to presentation {presentation.public_id}")
        else:
            collab.role = CollaboratorRole.EDITOR.value
            await session.flush()
            print(f"{COLLAB_EMAIL} already collaborator with role {collab.role}")

        print("\nSEEDING COMPLETE SUCCESSFULLY!")
        print(f"Owner: {OWNER_EMAIL} / {TEST_PASSWORD}")
        print(f"Collaborator: {COLLAB_EMAIL} / {TEST_PASSWORD}")
        print(f"Presentation Public ID: {presentation.public_id}")
        print(f"Presentation Title: {presentation.title}")


if __name__ == "__main__":
    asyncio.run(seed())
