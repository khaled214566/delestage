import enum

class PriorityLevel(str, enum.Enum):
    P0 = "P0"  # Never shed (hospitals, critical)
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"
    P4 = "P4"  
    P5 = "P5"  # First candidates for shedding

class FeederStatus(str, enum.Enum):
    CLOSED = "CLOSED"    # Normal, energized
    OPEN = "OPEN"        # Currently being shed
    MAINTENANCE = "MAINTENANCE"
    UNAVAILABLE = "UNAVAILABLE"

class OrderStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class OrderType(str, enum.Enum):
    J_1 = "J-1"          # Day-ahead plan
    REAL_TIME = "REAL_TIME"  # Real-time adjustment

class UserRole(str, enum.Enum):
    DISPATCHER = "DISPATCHER"
    CRC_OPERATOR = "CRC_OPERATOR"
    BCC_OPERATOR = "BCC_OPERATOR"
    ADMIN = "ADMIN"

class DeficitPlanStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"