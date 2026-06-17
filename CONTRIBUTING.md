# Contributing to Policy and Events Visualization Tool

## Contributing In General

Our project welcomes external contributions. If you have an itch, please feel free to scratch it.

To contribute code or documentation, please submit a [pull request](https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/pulls).

A good way to familiarize yourself with the codebase and contribution process is to look for and tackle low-hanging fruit in the [issue tracker](https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/issues). Before embarking on a more ambitious contribution, please quickly [get in touch](#communication) with us.

**Note: We appreciate your effort, and want to avoid a situation where a contribution requires extensive rework (by you or by us), sits in backlog for a long time, or cannot be accepted at all!**

## Proposing New Features

If you would like to implement a new feature, please [raise an issue](https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/issues) before sending a pull request so the feature can be discussed. This is to avoid you wasting your valuable time working on a feature that the project developers are not interested in accepting into the code base.

## Fixing Bugs

If you would like to fix a bug, please [raise an issue](https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/issues) before sending a pull request so it can be tracked.

## Merge Approval

The project maintainers use LGTM (Looks Good To Me) in comments on the code review to indicate acceptance. A change requires LGTMs from two of the maintainers of each component affected.

For a list of the maintainers, see the [MAINTAINERS.md](MAINTAINERS.md) page.

## Legal

Each source file must include a license header for the Apache Software License 2.0. Using the SPDX format is the simplest approach.

### Python and Shell Scripts

```python
#
# Copyright IBM Corp. 2024 - 2026
# SPDX-License-Identifier: Apache-2.0
#
```

### JavaScript and CSS

```javascript
/*
 * Copyright IBM Corp. 2024 - 2026
 * SPDX-License-Identifier: Apache-2.0
 */
```

We have tried to make it as easy as possible to make contributions. This applies to how we handle the legal aspects of contribution. We use the same approach - the [Developer's Certificate of Origin 1.1 (DCO)](https://github.com/hyperledger/fabric/blob/master/docs/source/DCO1.1.txt) - that the Linux® Kernel [community](https://elinux.org/Developer_Certificate_Of_Origin) uses to manage code contributions.

We simply ask that when submitting a patch for review, the developer must include a sign-off statement in the commit message.

Here is an example Signed-off-by line, which indicates that the submitter accepts the DCO:

```
Signed-off-by: John Doe <john.doe@example.com>
```

You can include this automatically when you commit a change to your local git repository using the following command:

```bash
git commit -s
```

## Communication

For questions or discussions, please:
- Open an issue in the [issue tracker](https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts/issues)
- Contact the project maintainers listed in [MAINTAINERS.md](MAINTAINERS.md)

## Setup

### Prerequisites

- Python 3.9+
- Access to Cassandra database (for data extraction)
- OpenShift/Kubernetes cluster (for deployment)

### Development Setup

1. Clone the repository:
   ```bash
   git clone https://github.ibm.com/hdm/noi-aiops-helping-tools-scripts.git
   cd noi-aiops-helping-tools-scripts/policies_and_events_visualization
   ```

2. Install dependencies:
   ```bash
   cd src
   pip install -r requirements.txt
   ```

3. Set up user credentials:
   ```bash
   python manage_users.py add <username>
   ```

4. Run locally:
   ```bash
   ./run_local.sh
   ```

For detailed installation instructions, see [docs/INSTALL.md](docs/INSTALL.md).

## Testing

### Manual Testing

1. Start the web interface:
   ```bash
   cd src
   python web_interface.py
   ```

2. Access the application at `http://localhost:5000`

3. Test key features:
   - Login with created user credentials
   - View policy summary table
   - View events detail table
   - Test search and filtering
   - Test export functionality

### Testing Changes

Before submitting a pull request:

1. **Test locally**: Run the application and verify your changes work as expected
2. **Check for errors**: Review logs for any errors or warnings
3. **Test edge cases**: Try invalid inputs, empty data sets, etc.
4. **Verify documentation**: Update relevant documentation if needed
5. **Check code style**: Follow Python PEP 8 guidelines

## Coding Style Guidelines

### Python

- Follow [PEP 8](https://pep8.org/) style guide
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and concise
- Use type hints where appropriate

### JavaScript

- Use consistent indentation (2 or 4 spaces)
- Use meaningful variable names
- Add comments for complex logic
- Follow existing code patterns in the project

### Shell Scripts

- Use `#!/bin/bash` shebang
- Add comments explaining complex commands
- Use meaningful variable names in UPPER_CASE
- Check exit codes and handle errors

### Documentation

- Use Markdown for all documentation
- Keep line length reasonable (80-100 characters)
- Use clear, concise language
- Include code examples where helpful
- Update table of contents when adding sections

## Pull Request Process

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add SPDX license headers to new files
5. Test your changes thoroughly
6. Commit your changes with DCO sign-off (`git commit -s -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request with:
   - Clear description of changes
   - Reference to related issues
   - Test results or screenshots if applicable

## Code Review Process

1. Maintainers will review your pull request
2. Address any feedback or requested changes
3. Once approved (LGTM from 2 maintainers), your PR will be merged
4. Your contribution will be included in the next release

## Questions?

If you have questions about contributing, please open an issue or contact the maintainers listed in [MAINTAINERS.md](MAINTAINERS.md).

Thank you for contributing to the Policy and Events Visualization Tool!