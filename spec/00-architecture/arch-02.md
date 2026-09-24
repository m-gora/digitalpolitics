# Scope Based RBAC
Write access shall be protected and only allowed to members of the respective district.

Read access is global: any authenticated user may read any district's data. Only writes are scoped.

Access to a district implies access to all districts beneath it in the hierarchy (e.g. membership of a Landesverband grants write access to its Bezirksverbände and Ortsvereine). See adr-03 for how this inheritance is resolved.