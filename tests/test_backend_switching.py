import pytest
from pathlib import Path
from unittest.mock import MagicMock
from rcds.project import Project

@pytest.fixture
def mock_project(tmp_path):
    # Create a mock project structure
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / "rcds.yaml").write_text("""
docker:
  image:
    prefix: test
backends:
  - resolve: k8s
    options:
      domain: k8s.example.com
      namespaceTemplate: "ns-{{ challenge.id }}"
  - resolve: instancer
    options:
      url: http://instancer.example.com
      login_secret_key: "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
      admin_team_id: "admin"
""")
    
    # Create mock challenges
    (project_root / "chall1").mkdir()
    (project_root / "chall1" / "challenge.yaml").write_text("""
name: Challenge 1
description: Desc
exposed: true
backend: k8s
containers:
  main:
    image: nginx
""")

    (project_root / "chall2").mkdir()
    (project_root / "chall2" / "challenge.yaml").write_text("""
name: Challenge 2
description: Desc
exposed: true
backend: instancer
containers:
  main:
    image: nginx
""")

    (project_root / "chall3").mkdir()
    (project_root / "chall3" / "challenge.yaml").write_text("""
name: Challenge 3
description: Desc
exposed: true
# No backend specified, should use default or first
containers:
  main:
    image: nginx
""")

    return Project(project_root)

def test_backend_selection(mock_project):
    mock_project.load_backends()
    mock_project.load_all_challenges()

    challenges = {c.config['name']: c for c in mock_project.challenges.values()}
    
    chall1 = challenges['Challenge 1']
    backend1 = mock_project.get_backend_for_challenge(chall1)
    backend_name1 = mock_project.get_backend_name_for_challenge(chall1)
    print(f"Chall1 backend: {backend_name1}")
    assert backend_name1 == 'k8s'
    assert backend1.__class__.__name__ == 'ContainerBackend' # k8s backend

    chall2 = challenges['Challenge 2']
    backend2 = mock_project.get_backend_for_challenge(chall2)
    backend_name2 = mock_project.get_backend_name_for_challenge(chall2)
    print(f"Chall2 backend: {backend_name2}")
    assert backend_name2 == 'instancer'
    assert backend2.__class__.__name__ == 'ContainerBackend' # instancer backend

    chall3 = challenges['Challenge 3']
    backend3 = mock_project.get_backend_for_challenge(chall3)
    backend_name3 = mock_project.get_backend_name_for_challenge(chall3)
    print(f"Chall3 backend: {backend_name3}")
    # Default behavior: first backend if defaultContainerBackend not set
    assert backend_name3 == 'k8s' 
