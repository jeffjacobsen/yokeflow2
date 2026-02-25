"""
Configuration Management
========================

Centralized configuration for YokeFlow.
Supports YAML configuration files with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
import yaml

# Load environment variables from .env file in agent root directory
# CRITICAL: Do NOT load from CWD, which might be a generated project directory
from dotenv import load_dotenv

# Get project root directory (parent.parent.parent from this file location)
_project_root = Path(__file__).parent.parent.parent
_agent_env_file = _project_root / ".env"

# Load from agent's .env only, not from any project directory
load_dotenv(dotenv_path=_agent_env_file)


@dataclass
class ModelConfig:
    """Configuration for Claude models."""
    initializer: str = field(default_factory=lambda: os.getenv(
        "DEFAULT_INITIALIZER_MODEL",
        "claude-opus-4-6"
    ))
    coding: str = field(default_factory=lambda: os.getenv(
        "DEFAULT_CODING_MODEL",
        "claude-sonnet-4-6"
    ))
    review: str = field(default_factory=lambda: os.getenv(
        "DEFAULT_REVIEW_MODEL",
        "claude-sonnet-4-6"
    ))
    prompt_improvement: str = field(default_factory=lambda: os.getenv(
        "DEFAULT_PROMPT_IMPROVEMENT_MODEL",
        "claude-opus-4-6"
    ))


@dataclass
class TimingConfig:
    """Configuration for timing and delays."""
    auto_continue_delay: int = 3  # seconds between sessions
    web_ui_poll_interval: int = 5  # seconds for UI refresh
    web_ui_port: int = 3010
    initialization_max_retries: int = 2  # number of attempts if initialization fails to start


@dataclass
class SecurityConfig:
    """Configuration for security settings."""
    additional_blocked_commands: List[str] = field(default_factory=list)


@dataclass
class DatabaseConfig:
    """Configuration for database settings."""
    database_url: str = field(default_factory=lambda: os.getenv(
        "DATABASE_URL",
        "postgresql://agent:agent_dev_password@localhost:5432/yokeflow"
    ))


@dataclass
class ProjectConfig:
    """Configuration for project settings."""
    default_projects_dir: str = "projects"
    max_iterations: Optional[int] = None  # None = unlimited


@dataclass
class ReviewConfig:
    """Configuration for review and prompt improvement settings."""
    min_reviews_for_analysis: int = 5  # Minimum deep reviews required for prompt improvement analysis


@dataclass
class InterventionConfig:
    """Configuration for intervention and retry management."""
    enabled: bool = False  # Enable/disable intervention system
    max_retries: int = 3  # Maximum retry attempts before blocking


@dataclass
class VerificationConfig:
    """Configuration for task verification system."""
    enabled: bool = True  # Enable/disable task verification
    auto_retry: bool = True  # Automatically retry failed tests
    max_retries: int = 3  # Maximum retry attempts for failed tests
    test_timeout: int = 30  # Timeout for individual tests in seconds
    require_all_tests_pass: bool = True  # Whether all tests must pass
    min_test_coverage: float = 0.8  # Minimum required test coverage (0.0 to 1.0)

    # Test generation settings
    generate_unit_tests: bool = True
    generate_api_tests: bool = True
    generate_browser_tests: bool = True
    generate_integration_tests: bool = False  # More complex, disabled by default

    # File tracking
    track_file_modifications: bool = True  # Track files modified during tasks

    # Notification settings
    webhook_url: Optional[str] = field(default_factory=lambda: os.getenv("YOKEFLOW_WEBHOOK_URL"))

    # Auto-pause conditions
    error_rate_threshold: float = 0.15  # Pause if error rate > 15%
    session_duration_limit: int = 600  # Pause after 10 minutes on same task
    detect_infrastructure_errors: bool = True  # Pause on Redis/DB/Prisma errors


@dataclass
class EpicTestingConfig:
    """Configuration for epic testing policies."""
    mode: str = 'autonomous'  # 'strict' or 'autonomous'

    # Strict mode settings
    strict_block_on_failure: bool = True
    strict_require_all_pass: bool = True
    strict_notify_on_block: bool = True
    strict_max_fix_attempts: int = 2

    # Autonomous mode settings
    auto_block_on_critical: bool = True
    auto_failure_tolerance: int = 3
    auto_continue_on_failure: bool = True
    auto_create_fix_tasks: bool = True

    # Critical epic patterns (substring match)
    critical_epics: List[str] = field(default_factory=lambda: [
        'Authentication', 'Database', 'Payment', 'Security', 'Core API'
    ])

    # Regression testing
    regression_enabled: bool = False  # Disabled by default for now
    regression_frequency: int = 10
    regression_random_chance: float = 0.1
    regression_skip_screenshots: bool = True

    def is_critical_epic(self, epic_name: str) -> bool:
        """Check if an epic is considered critical."""
        epic_lower = epic_name.lower()
        return any(critical.lower() in epic_lower for critical in self.critical_epics)

    def should_block(self, epic_name: str, failure_count: int) -> bool:
        """Determine if epic should be blocked based on mode and failures."""
        if self.mode == 'strict':
            return self.strict_block_on_failure and failure_count > 0
        else:  # autonomous
            is_critical = self.is_critical_epic(epic_name)
            exceeds_tolerance = failure_count > self.auto_failure_tolerance
            return (is_critical and self.auto_block_on_critical) or exceeds_tolerance


@dataclass
class BrownfieldConfig:
    """Configuration for brownfield project settings."""
    default_feature_branch_prefix: str = "yokeflow/"
    run_existing_tests_before_changes: bool = True
    run_existing_tests_after_changes: bool = True


@dataclass
class SpecAnalysisConfig:
    """Optional pre-analysis of spec files before initialization."""
    enabled: bool = False                       # Disabled by default
    model: str = "claude-haiku-4-5-20251001"    # Cheap/fast model for summarization


@dataclass
class ParallelConfig:
    """Configuration for parallel agent execution."""
    enabled: bool = False           # Opt-in, disabled by default
    max_workers: int = 2            # Default 2 concurrent workers, hard cap at 4
    max_tasks_per_worker: Optional[int] = None  # None = unlimited (worker loops until no tasks)


@dataclass
class Config:
    """Main configuration class."""
    models: ModelConfig = field(default_factory=ModelConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    project: ProjectConfig = field(default_factory=ProjectConfig)
    review: ReviewConfig = field(default_factory=ReviewConfig)
    intervention: InterventionConfig = field(default_factory=InterventionConfig)
    verification: VerificationConfig = field(default_factory=VerificationConfig)
    epic_testing: EpicTestingConfig = field(default_factory=EpicTestingConfig)
    brownfield: BrownfieldConfig = field(default_factory=BrownfieldConfig)
    spec_analysis: SpecAnalysisConfig = field(default_factory=SpecAnalysisConfig)
    parallel: ParallelConfig = field(default_factory=ParallelConfig)

    @classmethod
    def load_from_file(cls, config_path: Path) -> 'Config':
        """
        Load configuration from YAML file.

        Args:
            config_path: Path to YAML config file

        Returns:
            Config instance with values from file merged with defaults
        """
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, 'r') as f:
            data = yaml.safe_load(f) or {}

        # Create config with defaults, then override with file values
        config = cls()

        # Override model settings
        if 'models' in data:
            if 'initializer' in data['models']:
                config.models.initializer = data['models']['initializer']
            if 'coding' in data['models']:
                config.models.coding = data['models']['coding']
            if 'review' in data['models']:
                config.models.review = data['models']['review']
            if 'prompt_improvement' in data['models']:
                config.models.prompt_improvement = data['models']['prompt_improvement']

        # Override timing settings
        if 'timing' in data:
            if 'auto_continue_delay' in data['timing']:
                config.timing.auto_continue_delay = data['timing']['auto_continue_delay']
            if 'web_ui_poll_interval' in data['timing']:
                config.timing.web_ui_poll_interval = data['timing']['web_ui_poll_interval']
            if 'web_ui_port' in data['timing']:
                config.timing.web_ui_port = data['timing']['web_ui_port']

        # Override security settings
        if 'security' in data:
            if 'additional_blocked_commands' in data['security']:
                config.security.additional_blocked_commands = data['security']['additional_blocked_commands']

        # Override database settings
        if 'database' in data:
            if 'database_url' in data['database']:
                config.database.database_url = data['database']['database_url']

        # Override project settings
        if 'project' in data:
            if 'default_projects_dir' in data['project']:
                config.project.default_projects_dir = data['project']['default_projects_dir']
            if 'max_iterations' in data['project']:
                config.project.max_iterations = data['project']['max_iterations']

        # Override review settings
        if 'review' in data:
            if 'min_reviews_for_analysis' in data['review']:
                config.review.min_reviews_for_analysis = data['review']['min_reviews_for_analysis']

        # Override epic_testing settings
        if 'epic_testing' in data:
            if 'mode' in data['epic_testing']:
                config.epic_testing.mode = data['epic_testing']['mode']
            if 'critical_epics' in data['epic_testing']:
                config.epic_testing.critical_epics = data['epic_testing']['critical_epics']
            if 'auto_failure_tolerance' in data['epic_testing']:
                config.epic_testing.auto_failure_tolerance = data['epic_testing']['auto_failure_tolerance']
            if 'auto_create_fix_tasks' in data['epic_testing']:
                config.epic_testing.auto_create_fix_tasks = data['epic_testing']['auto_create_fix_tasks']
            if 'strict_notify_on_block' in data['epic_testing']:
                config.epic_testing.strict_notify_on_block = data['epic_testing']['strict_notify_on_block']

        # Override brownfield settings
        if 'brownfield' in data:
            if 'default_feature_branch_prefix' in data['brownfield']:
                config.brownfield.default_feature_branch_prefix = data['brownfield']['default_feature_branch_prefix']
            if 'run_existing_tests_before_changes' in data['brownfield']:
                config.brownfield.run_existing_tests_before_changes = data['brownfield']['run_existing_tests_before_changes']
            if 'run_existing_tests_after_changes' in data['brownfield']:
                config.brownfield.run_existing_tests_after_changes = data['brownfield']['run_existing_tests_after_changes']

        # Override spec_analysis settings
        if 'spec_analysis' in data:
            if 'enabled' in data['spec_analysis']:
                config.spec_analysis.enabled = data['spec_analysis']['enabled']
            if 'model' in data['spec_analysis']:
                config.spec_analysis.model = data['spec_analysis']['model']

        # Override parallel settings
        if 'parallel' in data:
            if 'enabled' in data['parallel']:
                config.parallel.enabled = data['parallel']['enabled']
            if 'max_workers' in data['parallel']:
                config.parallel.max_workers = min(int(data['parallel']['max_workers']), 4)  # Hard cap at 4
            if 'max_tasks_per_worker' in data['parallel']:
                val = data['parallel']['max_tasks_per_worker']
                config.parallel.max_tasks_per_worker = int(val) if val is not None else None

        return config

    @classmethod
    def load_default(cls) -> 'Config':
        """
        Load default configuration.

        Looks for config files in this order:
        1. .yokeflow.yaml in current directory
        2. .yokeflow.yaml in home directory
        4. Default values (no file)

        Returns:
            Config instance
        """
        # Check current directory for new name
        current_dir_config = Path('.yokeflow.yaml')
        if current_dir_config.exists():
            return cls.load_from_file(current_dir_config)

        # Check home directory for new name
        home_config = Path.home() / '.yokeflow.yaml'
        if home_config.exists():
            return cls.load_from_file(home_config)

        # Use defaults
        return cls()

    def to_yaml(self) -> str:
        """
        Convert configuration to YAML string.

        Returns:
            YAML representation of config
        """
        data = {
            'models': {
                'initializer': self.models.initializer,
                'coding': self.models.coding,
            },
            'timing': {
                'auto_continue_delay': self.timing.auto_continue_delay,
                'web_ui_poll_interval': self.timing.web_ui_poll_interval,
                'web_ui_port': self.timing.web_ui_port,
            },
            'security': {
                'additional_blocked_commands': self.security.additional_blocked_commands,
            },
            'database': {
                'database_url': self.database.database_url,
            },
            'project': {
                'default_projects_dir': self.project.default_projects_dir,
                'max_iterations': self.project.max_iterations,
            },
            'review': {
                'min_reviews_for_analysis': self.review.min_reviews_for_analysis,
            },
        }
        return yaml.dump(data, default_flow_style=False, sort_keys=False)
