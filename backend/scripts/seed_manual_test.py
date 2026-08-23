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

TEACHER_EMAIL = "manualtest.teacher@example.com"
STUDENT_EMAIL = "manualtest.student@example.com"
TEST_PASSWORD = "ManualTest2026!"


async def seed():
    async with async_session_factory() as session, session.begin():
        # 1. Teacher account
        result = await session.execute(select(User).where(User.email == TEACHER_EMAIL))
        teacher = result.scalar_one_or_none()
        if not teacher:
            teacher = User(
                email=TEACHER_EMAIL,
                password_hash=hash_password(TEST_PASSWORD),
                name="Manual Test Teacher",
                role=UserRole.TEACHER.value,
                is_verified=True,
                is_active=True,
            )
            session.add(teacher)
            await session.flush()
            print(f"Created teacher: {teacher.id} ({TEACHER_EMAIL})")
        else:
            teacher.password_hash = hash_password(TEST_PASSWORD)
            teacher.role = UserRole.TEACHER.value
            teacher.is_verified = True
            teacher.is_active = True
            await session.flush()
            print(f"Updated existing teacher: {teacher.id}")

        # 2. Student account
        result = await session.execute(select(User).where(User.email == STUDENT_EMAIL))
        student = result.scalar_one_or_none()
        if not student:
            student = User(
                email=STUDENT_EMAIL,
                password_hash=hash_password(TEST_PASSWORD),
                name="Manual Test Student",
                role=UserRole.STUDENT.value,
                is_verified=True,
                is_active=True,
            )
            session.add(student)
            await session.flush()
            print(f"Created student: {student.id} ({STUDENT_EMAIL})")
        else:
            student.password_hash = hash_password(TEST_PASSWORD)
            student.role = UserRole.STUDENT.value
            student.is_verified = True
            student.is_active = True
            await session.flush()
            print(f"Updated existing student: {student.id}")

        # 3. Presentation owned by teacher
        pres_title = "[Manual Test] Introduction to Machine Learning & Neural Networks"
        result = await session.execute(
            select(Presentation).where(
                Presentation.owner_id == teacher.id,
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
                owner_id=teacher.id,
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

        # 5. Collaborator (Student as EDITOR)
        result = await session.execute(
            select(PresentationCollaborator).where(
                PresentationCollaborator.presentation_id == presentation.id,
                PresentationCollaborator.user_id == student.id,
            )
        )
        collab = result.scalar_one_or_none()
        if not collab:
            collab = PresentationCollaborator(
                presentation_id=presentation.id,
                user_id=student.id,
                role=CollaboratorRole.EDITOR.value,
            )
            session.add(collab)
            await session.flush()
            print(f"Added student {STUDENT_EMAIL} as EDITOR collaborator to presentation {presentation.public_id}")
        else:
            collab.role = CollaboratorRole.EDITOR.value
            await session.flush()
            print(f"Student {STUDENT_EMAIL} already collaborator with role {collab.role}")

        print("\nSEEDING COMPLETE SUCCESSFULLY!")
        print(f"Teacher: {TEACHER_EMAIL} / {TEST_PASSWORD}")
        print(f"Student: {STUDENT_EMAIL} / {TEST_PASSWORD}")
        print(f"Presentation Public ID: {presentation.public_id}")
        print(f"Presentation Title: {presentation.title}")


if __name__ == "__main__":
    asyncio.run(seed())
