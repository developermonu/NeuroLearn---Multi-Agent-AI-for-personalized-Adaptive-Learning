from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy import text
from app.config import settings
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Start with MySQL engine (lazy - doesn't connect yet)
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def init_db():
    global engine, AsyncSessionLocal

    # Try MySQL connection first
    try:
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Connected to MySQL database")
    except Exception as e:
        logger.warning(f"MySQL not available ({e}), falling back to SQLite")
        engine = create_async_engine(
            settings.SQLITE_URL,
            echo=False,
        )
        AsyncSessionLocal = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

    # Create all tables
    async with engine.begin() as conn:
        from app.models import user, course, learning_path, quiz
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")

    # Seed initial data if empty
    await _seed_initial_data()


async def _seed_initial_data():
    """Seed exam data if the database is empty."""
    from app.models.course import Exam, Syllabus, Topic, Question

    async with AsyncSessionLocal() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM exams"))
        count = result.scalar()
        if count and count > 0:
            logger.info(f"Database already has {count} exams, skipping seed")
            return

        logger.info("Seeding initial exam data...")

        exams_data = [
            {
                "id": str(uuid.uuid4()),
                "name": "AWS Solutions Architect Associate",
                "short_name": "AWS-SAA",
                "description": "Validate your ability to design and implement distributed systems on AWS",
                "category": "Cloud Computing",
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Certified Public Accountant",
                "short_name": "CPA",
                "description": "Professional certification for accountants in the United States",
                "category": "Finance & Accounting",
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Project Management Professional",
                "short_name": "PMP",
                "description": "Globally recognized project management certification by PMI",
                "category": "Project Management",
            },
            {
                "id": str(uuid.uuid4()),
                "name": "Graduate Management Admission Test",
                "short_name": "GMAT",
                "description": "Standardized exam for admission to graduate business programs",
                "category": "Graduate Admissions",
            },
        ]

        for exam_data in exams_data:
            exam = Exam(**exam_data, is_active=True, created_at=datetime.now(timezone.utc))
            session.add(exam)

        # Seed syllabus and topics for AWS-SAA
        aws_exam_id = exams_data[0]["id"]
        syllabus_id = str(uuid.uuid4())
        syllabus = Syllabus(
            id=syllabus_id,
            exam_id=aws_exam_id,
            structured_json="{}",
            version="1",
            created_at=datetime.now(timezone.utc),
        )
        session.add(syllabus)

        aws_topics = [
            ("Cloud Concepts & AWS Overview", "Design Secure Architectures", "high", 85.0, "understand", 3.0),
            ("IAM & Security", "Design Secure Architectures", "high", 90.0, "apply", 4.0),
            ("VPC & Networking", "Design Resilient Architectures", "high", 88.0, "apply", 5.0),
            ("EC2 & Compute", "Design High-Performing Architectures", "high", 82.0, "apply", 4.0),
            ("S3 & Storage", "Design High-Performing Architectures", "high", 80.0, "understand", 3.0),
            ("RDS & Databases", "Design High-Performing Architectures", "medium", 75.0, "apply", 3.5),
            ("Lambda & Serverless", "Design High-Performing Architectures", "medium", 70.0, "apply", 3.0),
            ("CloudFormation & IaC", "Design Cost-Optimized Architectures", "medium", 65.0, "apply", 2.5),
            ("CloudWatch & Monitoring", "Design Resilient Architectures", "medium", 60.0, "understand", 2.0),
            ("Route 53 & DNS", "Design Resilient Architectures", "low", 55.0, "remember", 1.5),
            ("ELB & Auto Scaling", "Design Resilient Architectures", "high", 78.0, "apply", 3.0),
            ("SQS, SNS & Messaging", "Design High-Performing Architectures", "medium", 62.0, "understand", 2.0),
        ]

        topic_ids = []
        for idx, (name, section, weight, impact, bloom, hours) in enumerate(aws_topics):
            topic_id = str(uuid.uuid4())
            topic_ids.append(topic_id)
            topic = Topic(
                id=topic_id,
                syllabus_id=syllabus_id,
                section_name=section,
                name=name,
                weight=weight,
                impact_score=impact,
                bloom_level=bloom,
                estimated_hours=hours,
                order_index=idx,
                created_at=datetime.now(timezone.utc),
            )
            session.add(topic)

        # Seed diagnostic questions for each topic
        difficulties = ["easy", "medium", "hard"]
        bloom_levels = ["remember", "understand", "apply"]
        question_templates = [
            ("What is the primary purpose of {topic}?",
             ["A) To manage billing", "B) To handle {topic} operations", "C) To monitor logs", "D) To deploy containers"],
             "B", "The primary purpose of {topic} is to handle its core operations within AWS infrastructure."),
            ("Which AWS service is most closely related to {topic}?",
             ["A) Amazon S3", "B) AWS Lambda", "C) The dedicated {topic} service", "D) Amazon SQS"],
             "C", "{topic} has a dedicated service within the AWS ecosystem for managing these operations."),
            ("In a production environment, how would you best implement {topic}?",
             ["A) Using a single AZ deployment", "B) Using multi-AZ with proper redundancy", "C) Without any monitoring", "D) Using on-premises only"],
             "B", "Best practice for {topic} in production involves multi-AZ deployment with proper redundancy for high availability."),
        ]

        for topic_idx, topic_id in enumerate(topic_ids):
            topic_name = aws_topics[topic_idx][0]
            for q_idx, (text_tmpl, opts_tmpl, correct, expl_tmpl) in enumerate(question_templates):
                import json as _json
                diff = difficulties[q_idx % 3]
                bloom = bloom_levels[q_idx % 3]
                irt_params = {"easy": (0.8, -1.0, 0.25), "medium": (1.0, 0.0, 0.2), "hard": (1.2, 1.0, 0.15)}
                a, b, c = irt_params[diff]
                question = Question(
                    id=str(uuid.uuid4()),
                    topic_id=topic_id,
                    question_text=text_tmpl.format(topic=topic_name),
                    options_json=_json.dumps([o.format(topic=topic_name) for o in opts_tmpl]),
                    correct_answer=correct,
                    explanation=expl_tmpl.format(topic=topic_name),
                    difficulty=diff,
                    bloom_level=bloom,
                    irt_a=a, irt_b=b, irt_c=c,
                    is_diagnostic=True,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(question)

        await session.commit()
        logger.info(f"Seeded {len(exams_data)} exams, {len(aws_topics)} topics, {len(aws_topics) * len(question_templates)} questions")
