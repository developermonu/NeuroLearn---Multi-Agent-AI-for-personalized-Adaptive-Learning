-- =====================================================================
-- NeuroLearn - Complete MySQL Database Schema
-- Database initialization script
-- =====================================================================

SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;
SET collation_connection = 'utf8mb4_unicode_ci';

CREATE DATABASE IF NOT EXISTS neurolearn
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE neurolearn;

-- =====================================================================
-- 1. USERS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    learning_style ENUM('visual', 'reading', 'practice', 'mixed') NOT NULL DEFAULT 'mixed',
    daily_study_minutes INT DEFAULT 60,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_users_email (email),
    INDEX idx_users_is_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 2. EXAMS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS exams (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    name VARCHAR(300) NOT NULL,
    code VARCHAR(50) NOT NULL UNIQUE,
    description TEXT DEFAULT NULL,
    category VARCHAR(100) NOT NULL,
    provider VARCHAR(200) DEFAULT NULL,
    difficulty_level ENUM('beginner', 'intermediate', 'advanced', 'expert') NOT NULL DEFAULT 'intermediate',
    estimated_study_hours INT DEFAULT NULL,
    passing_score DECIMAL(5,2) DEFAULT NULL,
    total_questions INT DEFAULT NULL,
    exam_duration_minutes INT DEFAULT NULL,
    exam_fee VARCHAR(100) DEFAULT NULL,
    official_url VARCHAR(500) DEFAULT NULL,
    icon_url VARCHAR(500) DEFAULT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    tags JSON DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_exams_code (code),
    INDEX idx_exams_category (category),
    INDEX idx_exams_is_active (is_active),
    INDEX idx_exams_difficulty (difficulty_level)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 3. ENROLLMENTS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS enrollments (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    exam_id VARCHAR(36) NOT NULL,
    status ENUM('active', 'paused', 'completed', 'dropped') NOT NULL DEFAULT 'active',
    target_date DATE DEFAULT NULL,
    enrolled_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    overall_progress DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    study_streak_days INT NOT NULL DEFAULT 0,
    total_study_minutes INT NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_enrollments_user_exam (user_id, exam_id),
    INDEX idx_enrollments_user_id (user_id),
    INDEX idx_enrollments_exam_id (exam_id),
    INDEX idx_enrollments_status (status),

    CONSTRAINT fk_enrollments_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_enrollments_exam FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 4. SYLLABI TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS syllabi (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    exam_id VARCHAR(36) NOT NULL,
    title VARCHAR(300) NOT NULL,
    description TEXT DEFAULT NULL,
    version VARCHAR(20) DEFAULT '1.0',
    source_type ENUM('ai_generated', 'manual', 'official') NOT NULL DEFAULT 'ai_generated',
    structure JSON DEFAULT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    generated_by VARCHAR(100) DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_syllabi_exam_id (exam_id),
    INDEX idx_syllabi_is_active (is_active),

    CONSTRAINT fk_syllabi_exam FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 5. TOPICS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS topics (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    syllabus_id VARCHAR(36) NOT NULL,
    parent_topic_id VARCHAR(36) DEFAULT NULL,
    title VARCHAR(300) NOT NULL,
    description TEXT DEFAULT NULL,
    order_index INT NOT NULL DEFAULT 0,
    depth_level INT NOT NULL DEFAULT 0,
    estimated_minutes INT DEFAULT NULL,
    weight_percentage DECIMAL(5,2) DEFAULT NULL,
    is_optional BOOLEAN NOT NULL DEFAULT FALSE,
    tags JSON DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_topics_syllabus_id (syllabus_id),
    INDEX idx_topics_parent_id (parent_topic_id),
    INDEX idx_topics_order (order_index),
    INDEX idx_topics_depth (depth_level),

    CONSTRAINT fk_topics_syllabus FOREIGN KEY (syllabus_id) REFERENCES syllabi(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_topics_parent FOREIGN KEY (parent_topic_id) REFERENCES topics(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 6. CONTENT ITEMS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS content_items (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    topic_id VARCHAR(36) NOT NULL,
    content_type ENUM('explanation', 'summary', 'example', 'key_points', 'mnemonic', 'analogy', 'diagram_description', 'code_snippet', 'reference') NOT NULL DEFAULT 'explanation',
    title VARCHAR(300) DEFAULT NULL,
    body TEXT NOT NULL,
    format ENUM('text', 'markdown', 'html', 'code') NOT NULL DEFAULT 'markdown',
    difficulty_level ENUM('beginner', 'intermediate', 'advanced') DEFAULT 'intermediate',
    language VARCHAR(10) NOT NULL DEFAULT 'en',
    ai_model VARCHAR(100) DEFAULT NULL,
    generation_prompt TEXT DEFAULT NULL,
    quality_score DECIMAL(3,2) DEFAULT NULL,
    order_index INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    metadata JSON DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_content_topic_id (topic_id),
    INDEX idx_content_type (content_type),
    INDEX idx_content_order (order_index),
    INDEX idx_content_language (language),
    INDEX idx_content_is_active (is_active),

    CONSTRAINT fk_content_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 7. QUESTIONS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS questions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    topic_id VARCHAR(36) NOT NULL,
    question_type ENUM('multiple_choice', 'multiple_select', 'true_false', 'fill_blank', 'short_answer', 'scenario_based') NOT NULL DEFAULT 'multiple_choice',
    difficulty ENUM('easy', 'medium', 'hard', 'expert') NOT NULL DEFAULT 'medium',
    question_text TEXT NOT NULL,
    options JSON DEFAULT NULL,
    correct_answer JSON NOT NULL,
    explanation TEXT DEFAULT NULL,
    hint TEXT DEFAULT NULL,
    points INT NOT NULL DEFAULT 1,
    time_limit_seconds INT DEFAULT 120,
    tags JSON DEFAULT NULL,
    ai_model VARCHAR(100) DEFAULT NULL,
    source ENUM('ai_generated', 'manual', 'imported') NOT NULL DEFAULT 'ai_generated',
    times_answered INT NOT NULL DEFAULT 0,
    times_correct INT NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_questions_topic_id (topic_id),
    INDEX idx_questions_type (question_type),
    INDEX idx_questions_difficulty (difficulty),
    INDEX idx_questions_is_active (is_active),

    CONSTRAINT fk_questions_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 8. DIAGNOSTIC RESULTS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS diagnostic_results (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    exam_id VARCHAR(36) NOT NULL,
    enrollment_id VARCHAR(36) DEFAULT NULL,
    diagnostic_type ENUM('initial', 'mid_term', 'pre_exam', 'custom') NOT NULL DEFAULT 'initial',
    total_questions INT NOT NULL DEFAULT 0,
    correct_answers INT NOT NULL DEFAULT 0,
    score_percentage DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    time_spent_seconds INT DEFAULT NULL,
    topic_scores JSON DEFAULT NULL,
    strengths JSON DEFAULT NULL,
    weaknesses JSON DEFAULT NULL,
    recommended_focus_areas JSON DEFAULT NULL,
    ai_analysis TEXT DEFAULT NULL,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_diagnostic_user_id (user_id),
    INDEX idx_diagnostic_exam_id (exam_id),
    INDEX idx_diagnostic_enrollment_id (enrollment_id),
    INDEX idx_diagnostic_type (diagnostic_type),

    CONSTRAINT fk_diagnostic_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_diagnostic_exam FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_diagnostic_enrollment FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 9. LEARNING PATHS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS learning_paths (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    enrollment_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    exam_id VARCHAR(36) NOT NULL,
    title VARCHAR(300) DEFAULT NULL,
    strategy ENUM('weakness_first', 'sequential', 'balanced', 'spaced_repetition', 'adaptive') NOT NULL DEFAULT 'balanced',
    total_estimated_hours DECIMAL(6,2) DEFAULT NULL,
    daily_study_minutes INT DEFAULT 120,
    path_data JSON DEFAULT NULL,
    topic_order JSON DEFAULT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    ai_reasoning TEXT DEFAULT NULL,
    generated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_learning_paths_enrollment (enrollment_id),
    INDEX idx_learning_paths_user (user_id),
    INDEX idx_learning_paths_exam (exam_id),
    INDEX idx_learning_paths_is_active (is_active),

    CONSTRAINT fk_learning_paths_enrollment FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_learning_paths_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_learning_paths_exam FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 10. SCHEDULE ITEMS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS schedule_items (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    learning_path_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    topic_id VARCHAR(36) DEFAULT NULL,
    title VARCHAR(300) NOT NULL,
    description TEXT DEFAULT NULL,
    item_type ENUM('study', 'review', 'quiz', 'practice_exam', 'break', 'milestone') NOT NULL DEFAULT 'study',
    scheduled_date DATE NOT NULL,
    start_time TIME DEFAULT NULL,
    end_time TIME DEFAULT NULL,
    duration_minutes INT NOT NULL DEFAULT 60,
    status ENUM('pending', 'in_progress', 'completed', 'skipped', 'rescheduled') NOT NULL DEFAULT 'pending',
    priority ENUM('low', 'medium', 'high', 'critical') NOT NULL DEFAULT 'medium',
    completed_at TIMESTAMP NULL DEFAULT NULL,
    notes TEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_schedule_path_id (learning_path_id),
    INDEX idx_schedule_user_id (user_id),
    INDEX idx_schedule_topic_id (topic_id),
    INDEX idx_schedule_date (scheduled_date),
    INDEX idx_schedule_status (status),
    INDEX idx_schedule_type (item_type),

    CONSTRAINT fk_schedule_path FOREIGN KEY (learning_path_id) REFERENCES learning_paths(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_schedule_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_schedule_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 11. QUIZ SESSIONS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS quiz_sessions (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    exam_id VARCHAR(36) NOT NULL,
    enrollment_id VARCHAR(36) DEFAULT NULL,
    topic_id VARCHAR(36) DEFAULT NULL,
    session_type ENUM('practice', 'diagnostic', 'topic_quiz', 'mock_exam', 'review', 'adaptive') NOT NULL DEFAULT 'practice',
    total_questions INT NOT NULL DEFAULT 0,
    answered_questions INT NOT NULL DEFAULT 0,
    correct_answers INT NOT NULL DEFAULT 0,
    score_percentage DECIMAL(5,2) DEFAULT NULL,
    time_spent_seconds INT NOT NULL DEFAULT 0,
    time_limit_seconds INT DEFAULT NULL,
    status ENUM('in_progress', 'completed', 'abandoned', 'timed_out') NOT NULL DEFAULT 'in_progress',
    difficulty_level ENUM('easy', 'medium', 'hard', 'mixed', 'adaptive') DEFAULT 'mixed',
    settings JSON DEFAULT NULL,
    started_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_quiz_sessions_user (user_id),
    INDEX idx_quiz_sessions_exam (exam_id),
    INDEX idx_quiz_sessions_enrollment (enrollment_id),
    INDEX idx_quiz_sessions_topic (topic_id),
    INDEX idx_quiz_sessions_type (session_type),
    INDEX idx_quiz_sessions_status (status),

    CONSTRAINT fk_quiz_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_quiz_sessions_exam FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_quiz_sessions_enrollment FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_quiz_sessions_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 12. QUIZ ANSWERS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS quiz_answers (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    quiz_session_id VARCHAR(36) NOT NULL,
    question_id VARCHAR(36) NOT NULL,
    user_id VARCHAR(36) NOT NULL,
    selected_answer JSON DEFAULT NULL,
    is_correct BOOLEAN NOT NULL DEFAULT FALSE,
    time_spent_seconds INT DEFAULT NULL,
    confidence_level ENUM('low', 'medium', 'high') DEFAULT NULL,
    is_flagged BOOLEAN NOT NULL DEFAULT FALSE,
    answer_order INT NOT NULL DEFAULT 0,
    answered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_quiz_answers_session (quiz_session_id),
    INDEX idx_quiz_answers_question (question_id),
    INDEX idx_quiz_answers_user (user_id),
    INDEX idx_quiz_answers_is_correct (is_correct),

    CONSTRAINT fk_quiz_answers_session FOREIGN KEY (quiz_session_id) REFERENCES quiz_sessions(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_quiz_answers_question FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_quiz_answers_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 13. USER TOPIC PROGRESS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS user_topic_progress (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    topic_id VARCHAR(36) NOT NULL,
    enrollment_id VARCHAR(36) DEFAULT NULL,
    mastery_level ENUM('not_started', 'beginner', 'developing', 'proficient', 'mastered') NOT NULL DEFAULT 'not_started',
    mastery_score DECIMAL(5,2) NOT NULL DEFAULT 0.00,
    study_time_minutes INT NOT NULL DEFAULT 0,
    content_viewed INT NOT NULL DEFAULT 0,
    total_content INT NOT NULL DEFAULT 0,
    questions_attempted INT NOT NULL DEFAULT 0,
    questions_correct INT NOT NULL DEFAULT 0,
    quiz_avg_score DECIMAL(5,2) DEFAULT NULL,
    last_studied_at TIMESTAMP NULL DEFAULT NULL,
    next_review_at TIMESTAMP NULL DEFAULT NULL,
    spaced_repetition_interval INT DEFAULT NULL,
    ease_factor DECIMAL(4,2) DEFAULT 2.50,
    review_count INT NOT NULL DEFAULT 0,
    notes TEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    UNIQUE KEY uk_user_topic_progress (user_id, topic_id, enrollment_id),
    INDEX idx_progress_user (user_id),
    INDEX idx_progress_topic (topic_id),
    INDEX idx_progress_enrollment (enrollment_id),
    INDEX idx_progress_mastery (mastery_level),
    INDEX idx_progress_next_review (next_review_at),

    CONSTRAINT fk_progress_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_progress_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_progress_enrollment FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 14. QA CONVERSATIONS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS qa_conversations (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    exam_id VARCHAR(36) DEFAULT NULL,
    topic_id VARCHAR(36) DEFAULT NULL,
    title VARCHAR(300) DEFAULT NULL,
    status ENUM('active', 'archived', 'deleted') NOT NULL DEFAULT 'active',
    message_count INT NOT NULL DEFAULT 0,
    ai_model VARCHAR(100) DEFAULT NULL,
    context_metadata JSON DEFAULT NULL,
    last_message_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_qa_conv_user (user_id),
    INDEX idx_qa_conv_exam (exam_id),
    INDEX idx_qa_conv_topic (topic_id),
    INDEX idx_qa_conv_status (status),
    INDEX idx_qa_conv_last_message (last_message_at),

    CONSTRAINT fk_qa_conv_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_qa_conv_exam FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_qa_conv_topic FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 15. QA MESSAGES TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS qa_messages (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    conversation_id VARCHAR(36) NOT NULL,
    role ENUM('user', 'assistant', 'system') NOT NULL,
    content TEXT NOT NULL,
    content_type ENUM('text', 'markdown', 'code', 'mixed') NOT NULL DEFAULT 'text',
    ai_model VARCHAR(100) DEFAULT NULL,
    tokens_used INT DEFAULT NULL,
    response_time_ms INT DEFAULT NULL,
    feedback ENUM('helpful', 'not_helpful', 'reported') DEFAULT NULL,
    sources JSON DEFAULT NULL,
    metadata JSON DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_qa_msg_conversation (conversation_id),
    INDEX idx_qa_msg_role (role),
    INDEX idx_qa_msg_created (created_at),

    CONSTRAINT fk_qa_msg_conversation FOREIGN KEY (conversation_id) REFERENCES qa_conversations(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 16. NOTIFICATIONS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS notifications (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    title VARCHAR(300) NOT NULL,
    message TEXT NOT NULL,
    notification_type ENUM('study_reminder', 'quiz_complete', 'achievement', 'streak', 'schedule', 'system', 'ai_insight', 'milestone') NOT NULL DEFAULT 'system',
    priority ENUM('low', 'medium', 'high', 'urgent') NOT NULL DEFAULT 'medium',
    is_read BOOLEAN NOT NULL DEFAULT FALSE,
    read_at TIMESTAMP NULL DEFAULT NULL,
    action_url VARCHAR(500) DEFAULT NULL,
    icon VARCHAR(50) DEFAULT NULL,
    metadata JSON DEFAULT NULL,
    expires_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_notifications_user (user_id),
    INDEX idx_notifications_type (notification_type),
    INDEX idx_notifications_is_read (is_read),
    INDEX idx_notifications_created (created_at),
    INDEX idx_notifications_expires (expires_at),

    CONSTRAINT fk_notifications_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 17. AGENT TASK LOGS TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS agent_task_logs (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) DEFAULT NULL,
    agent_type ENUM('syllabus_generator', 'content_creator', 'question_generator', 'diagnostic_analyzer', 'path_planner', 'qa_assistant', 'progress_tracker', 'scheduler', 'certificate_generator', 'web_researcher') NOT NULL,
    task_name VARCHAR(300) NOT NULL,
    task_description TEXT DEFAULT NULL,
    status ENUM('pending', 'running', 'completed', 'failed', 'cancelled', 'retrying') NOT NULL DEFAULT 'pending',
    input_data JSON DEFAULT NULL,
    output_data JSON DEFAULT NULL,
    error_message TEXT DEFAULT NULL,
    error_traceback TEXT DEFAULT NULL,
    ai_model VARCHAR(100) DEFAULT NULL,
    tokens_input INT DEFAULT NULL,
    tokens_output INT DEFAULT NULL,
    cost_usd DECIMAL(10,6) DEFAULT NULL,
    execution_time_ms INT DEFAULT NULL,
    retry_count INT NOT NULL DEFAULT 0,
    max_retries INT NOT NULL DEFAULT 3,
    parent_task_id VARCHAR(36) DEFAULT NULL,
    celery_task_id VARCHAR(255) DEFAULT NULL,
    started_at TIMESTAMP NULL DEFAULT NULL,
    completed_at TIMESTAMP NULL DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_agent_logs_user (user_id),
    INDEX idx_agent_logs_type (agent_type),
    INDEX idx_agent_logs_status (status),
    INDEX idx_agent_logs_parent (parent_task_id),
    INDEX idx_agent_logs_celery (celery_task_id),
    INDEX idx_agent_logs_created (created_at),

    CONSTRAINT fk_agent_logs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL ON UPDATE CASCADE,
    CONSTRAINT fk_agent_logs_parent FOREIGN KEY (parent_task_id) REFERENCES agent_task_logs(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================================
-- 18. CERTIFICATES TABLE
-- =====================================================================
CREATE TABLE IF NOT EXISTS certificates (
    id VARCHAR(36) NOT NULL PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL,
    exam_id VARCHAR(36) NOT NULL,
    enrollment_id VARCHAR(36) DEFAULT NULL,
    certificate_number VARCHAR(50) NOT NULL UNIQUE,
    title VARCHAR(300) NOT NULL,
    description TEXT DEFAULT NULL,
    issued_date DATE NOT NULL,
    expiry_date DATE DEFAULT NULL,
    final_score DECIMAL(5,2) NOT NULL,
    total_study_hours DECIMAL(8,2) DEFAULT NULL,
    topics_mastered INT DEFAULT NULL,
    total_topics INT DEFAULT NULL,
    quizzes_completed INT DEFAULT NULL,
    average_quiz_score DECIMAL(5,2) DEFAULT NULL,
    pdf_url VARCHAR(500) DEFAULT NULL,
    qr_code_data VARCHAR(500) DEFAULT NULL,
    verification_url VARCHAR(500) DEFAULT NULL,
    template_version VARCHAR(20) DEFAULT '1.0',
    metadata JSON DEFAULT NULL,
    is_valid BOOLEAN NOT NULL DEFAULT TRUE,
    revoked_at TIMESTAMP NULL DEFAULT NULL,
    revocation_reason TEXT DEFAULT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_certificates_user (user_id),
    INDEX idx_certificates_exam (exam_id),
    INDEX idx_certificates_enrollment (enrollment_id),
    INDEX idx_certificates_number (certificate_number),
    INDEX idx_certificates_issued (issued_date),
    INDEX idx_certificates_valid (is_valid),

    CONSTRAINT fk_certificates_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_certificates_exam FOREIGN KEY (exam_id) REFERENCES exams(id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_certificates_enrollment FOREIGN KEY (enrollment_id) REFERENCES enrollments(id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- =====================================================================
-- SEED DATA
-- =====================================================================

-- -----------------------------------------------------------------
-- Seed: Sample Exams
-- -----------------------------------------------------------------
INSERT INTO exams (id, name, code, description, category, provider, difficulty_level, estimated_study_hours, passing_score, total_questions, exam_duration_minutes, exam_fee, official_url, is_active, tags) VALUES
(
    '550e8400-e29b-41d4-a716-446655440001',
    'AWS Certified Solutions Architect - Associate',
    'AWS-SAA-C03',
    'Validates the ability to design and implement distributed systems on AWS. Covers compute, networking, storage, database services, architectural best practices, and cost optimization strategies.',
    'Cloud Computing',
    'Amazon Web Services (AWS)',
    'intermediate',
    150,
    72.00,
    65,
    130,
    '$150 USD',
    'https://aws.amazon.com/certification/certified-solutions-architect-associate/',
    TRUE,
    '["aws", "cloud", "architecture", "solutions-architect", "associate"]'
),
(
    '550e8400-e29b-41d4-a716-446655440002',
    'Certified Public Accountant',
    'CPA-EXAM',
    'The Uniform CPA Examination tests the knowledge and skills entry-level CPAs need. Covers auditing, business environment, financial accounting, and regulation.',
    'Finance & Accounting',
    'AICPA (American Institute of CPAs)',
    'advanced',
    400,
    75.00,
    276,
    960,
    '$1,000+ USD (all sections)',
    'https://www.aicpa.org/resources/article/the-cpa-exam',
    TRUE,
    '["accounting", "finance", "cpa", "audit", "tax", "regulation"]'
),
(
    '550e8400-e29b-41d4-a716-446655440003',
    'Project Management Professional',
    'PMP',
    'The PMP certification validates competence in leading and directing projects. Covers predictive, agile, and hybrid project management approaches across people, process, and business domains.',
    'Project Management',
    'Project Management Institute (PMI)',
    'advanced',
    200,
    60.00,
    180,
    230,
    '$555 USD (PMI member) / $405 USD (non-member)',
    'https://www.pmi.org/certifications/project-management-pmp',
    TRUE,
    '["project-management", "pmp", "agile", "leadership", "pmi"]'
),
(
    '550e8400-e29b-41d4-a716-446655440004',
    'Graduate Management Admission Test',
    'GMAT',
    'The GMAT exam measures analytical writing, integrated reasoning, quantitative, and verbal skills for graduate management program admissions. Widely accepted by business schools worldwide.',
    'Graduate Admissions',
    'Graduate Management Admission Council (GMAC)',
    'advanced',
    250,
    NULL,
    80,
    135,
    '$275 USD',
    'https://www.mba.com/exams/gmat-exam',
    TRUE,
    '["gmat", "mba", "business-school", "quantitative", "verbal", "analytical"]'
);

-- -----------------------------------------------------------------
-- Seed: Admin User (password: admin123 - change in production!)
-- Bcrypt hash for 'admin123'
-- -----------------------------------------------------------------
INSERT INTO users (id, email, full_name, password_hash, learning_style, daily_study_minutes, is_active) VALUES
(
    '550e8400-e29b-41d4-a716-446655440099',
    'admin@neurolearn.com',
    'NeuroLearn Admin',
    '$2b$12$LJ3m4ys3GZfnMRqzLOhSce7JR0sBDPMi5bXQbKkklDYE8M4qavbW2',
    'mixed',
    120,
    TRUE
);
