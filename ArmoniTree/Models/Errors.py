class ArmoniTreeError(Exception):
    pass


class ValidationError(ArmoniTreeError):
    pass


class NodeNotFoundError(ArmoniTreeError):
    pass


class DuplicateNodeError(ArmoniTreeError):
    pass


class ProtectedRootError(ArmoniTreeError):
    pass


class PersistenceError(ArmoniTreeError):
    pass


class InvalidTreeDataError(PersistenceError):
    pass
