# Security Updates

## Dependency Vulnerability Fixes

### Date: 2026-05-25

**Issue**: GitHub Dependabot detected 21 vulnerabilities in Python dependencies:
- 4 High severity
- 16 Moderate severity
- 1 Low severity

### Actions Taken

Updated `src/requirements.txt` with latest stable versions and version constraints:

#### Updated Packages

1. **scylla-driver**: `>=3.25.0` → `>=3.29.1,<4.0.0`
   - Updated to latest stable version
   - Added upper bound to prevent breaking changes

2. **orjson**: `>=3.6.0` → `>=3.10.7,<4.0.0`
   - Updated to latest stable version
   - Improved JSON parsing security

3. **psutil**: `>=5.9.0` → `>=6.1.0,<7.0.0`
   - Major version update to address security vulnerabilities
   - Maintains backward compatibility for our use cases

4. **tqdm**: `>=4.65.0` → `>=4.67.1,<5.0.0`
   - Updated to latest stable version
   - Minor security improvements

5. **pandas**: `>=1.3.0` → `>=2.2.3,<3.0.0`
   - Major version update to address multiple CVEs
   - Note: pandas has many transitive dependencies that may trigger alerts
   - Only used in optional test/generation scripts

### Version Constraint Strategy

The updated requirements.txt uses semantic versioning constraints:
- `>=X.Y.Z,<MAJOR+1.0.0` format
- Allows automatic security patches (patch updates)
- Allows minor version updates with new features
- Prevents breaking changes from major version updates

### Verification Steps

After updating dependencies, users should:

1. **Update packages**:
   ```bash
   pip install --upgrade -r requirements.txt
   ```

2. **Verify installation**:
   ```bash
   pip list | grep -E "scylla-driver|orjson|psutil|tqdm|pandas"
   ```

3. **Test functionality**:
   ```bash
   # Test data extraction
   python copy_policies_details_from_cassandra.py --help
   
   # Test processing
   python process_policies_and_events.py --help
   
   # Test web interface
   python web_interface.py
   ```

4. **Lock versions for production** (optional):
   ```bash
   pip freeze > requirements-lock.txt
   ```

### Impact Assessment

- **Web Interface**: No impact - uses only Python standard library
- **Data Extraction Scripts**: Requires package updates
- **Processing Scripts**: Requires package updates
- **Test/Generation Scripts**: Requires package updates (pandas)

### Future Monitoring

- Enable Dependabot alerts in repository settings
- Review security advisories monthly
- Update dependencies quarterly or when critical vulnerabilities are discovered
- Consider using `pip-audit` for automated vulnerability scanning:
  ```bash
  pip install pip-audit
  pip-audit -r requirements.txt
  ```

### Additional Security Measures

1. **Added SPDX license headers** to all source files
2. **Created SECURITY.md** with vulnerability reporting process
3. **Implemented version constraints** to balance security and stability
4. **Documented update procedures** in this file

### References

- [Python Package Index (PyPI)](https://pypi.org/)
- [GitHub Dependabot Documentation](https://docs.github.com/en/code-security/dependabot)
- [NIST National Vulnerability Database](https://nvd.nist.gov/)
- [pip-audit Tool](https://github.com/pypa/pip-audit)

---

**Note**: This document will be updated as new vulnerabilities are discovered and addressed.