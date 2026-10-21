DEFAULT_TIMEOUT = 180

TARGET = {
    "type": "string",
    "description": "Configured remote host name (one of the targets under this plugin's settings in config.yaml).",
}

TERMINAL = {
    "name": "terminal_remote",
    "description": (
        "Execute shell commands on a configured remote host over ssh (bash semantics; "
        "the remote login shell may be fish - commands still run under bash). "
        "Use it for hosts configured in this plugin's settings; "
        "the local machine is served by the built-in tools. "
        "Dangerous commands go through the same approval flow as the built-in terminal. "
        "background=true registers the process for completion notifications and standard process management. "
        'Invoke via tool_call as {"calls": [{"name": "terminal_remote", "arguments": {"target": ..., "command": ...}}]} - every parameter goes INSIDE the inner call\'s arguments object, one entry per tool_call; '
        "target as a sibling of arguments is rejected."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": TARGET,
            "command": {
                "type": "string",
                "description": "The shell command to execute.",
            },
            "workdir": {
                "type": "string",
                "description": "Working directory on the remote host.",
            },
            "timeout": {
                "type": "integer",
                "description": f"Max seconds to wait (default {DEFAULT_TIMEOUT}).",
            },
            "background": {
                "type": "boolean",
                "description": (
                    "Run in the background and return a session id immediately; "
                    "pair with the standard process management tool."
                ),
            },
        },
        "required": ["target", "command"],
    },
}

READ = {
    "name": "read_remote_file",
    "description": (
        "Read a text file on a configured remote host, with pagination and line numbers. "
        "Binary files are rejected with a type hint. "
        "Invoke via tool_call with one entry; "
        "all parameters (target, path, ...) go INSIDE the inner call's arguments object."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": TARGET,
            "path": {"type": "string", "description": "Absolute or ~-relative path."},
            "offset": {
                "type": "integer",
                "description": "Line number to start from (1-indexed).",
            },
            "limit": {"type": "integer", "description": "Maximum number of lines."},
        },
        "required": ["target", "path"],
    },
}

WRITE = {
    "name": "write_remote_file",
    "description": (
        "Create or overwrite a file on a configured remote host. "
        "The previous content is snapshotted first (undoable) and the write is verified by a read-back hash. "
        "Invoke via tool_call with one entry; "
        "all parameters (target, path, content) go INSIDE the inner call's arguments object."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": TARGET,
            "path": {"type": "string", "description": "File path on the remote host."},
            "content": {"type": "string", "description": "Complete new file content."},
        },
        "required": ["target", "path", "content"],
    },
}

PATCH = {
    "name": "patch_remote_file",
    "description": (
        "Targeted find-and-replace on a file of a configured remote host, with fuzzy matching. "
        "The previous content is snapshotted first (undoable). "
        "Invoke via tool_call with one entry; "
        "all parameters (target, path, old_string, new_string) go INSIDE the inner call's arguments object."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": TARGET,
            "path": {"type": "string", "description": "File path on the remote host."},
            "old_string": {"type": "string", "description": "Text to find."},
            "new_string": {"type": "string", "description": "Replacement text."},
            "replace_all": {
                "type": "boolean",
                "description": "Replace every occurrence.",
            },
        },
        "required": ["target", "path", "old_string", "new_string"],
    },
}

SEARCH = {
    "name": "search_remote_files",
    "description": (
        "Search files on a configured remote host by regex (content mode: inside files with line numbers; files mode: match paths by glob). "
        "Invoke via tool_call with one entry; "
        "all parameters (target, pattern, ...) go INSIDE the inner call's arguments object."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": TARGET,
            "pattern": {
                "type": "string",
                "description": "Regex (content) or glob (files).",
            },
            "path": {
                "type": "string",
                "description": "Directory or file to search (default .).",
            },
            "mode": {
                "type": "string",
                "enum": ["content", "files"],
                "description": "Search mode (default content).",
            },
            "file_glob": {
                "type": "string",
                "description": "Restrict content search to these files.",
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of results (default 50).",
            },
        },
        "required": ["target", "pattern"],
    },
}

UNDO = {
    "name": "undo_remote_file",
    "description": (
        "Restore the previous content of a remote file from this plugin's snapshot store. "
        "The content being replaced is itself snapshotted, so undo steps can be walked back one at a time. "
        "Invoke via tool_call with one entry; "
        "all parameters (target, path) go INSIDE the inner call's arguments object."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "target": TARGET,
            "path": {"type": "string", "description": "File path on the remote host."},
        },
        "required": ["target", "path"],
    },
}
