package main

import (
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func TestAuthorized(t *testing.T) {
	if !authorized("Bearer secret", "secret") {
		t.Fatal("expected valid bearer token")
	}
	for _, header := range []string{"", "secret", "Bearer wrong", "bearer secret"} {
		if authorized(header, "secret") {
			t.Fatalf("unexpected authorization for %q", header)
		}
	}
}

func TestSemverPattern(t *testing.T) {
	for _, tag := range []string{"v1.2.3", "v0.0.1-rc.1"} {
		if !semverPattern.MatchString(tag) {
			t.Errorf("expected valid tag %q", tag)
		}
	}
	for _, tag := range []string{"1.2.3", "latest", "v1.2", "v1.2.3;echo bad", "v1.2.3+build"} {
		if semverPattern.MatchString(tag) {
			t.Errorf("unexpected valid tag %q", tag)
		}
	}
}

func TestUpdateTagFile(t *testing.T) {
	path := filepath.Join(t.TempDir(), ".env")
	original := "DOMAIN=example.test\nDPP_TAG=v1.2.2\nSECRET=keep\n"
	if err := os.WriteFile(path, []byte(original), 0600); err != nil {
		t.Fatal(err)
	}
	if err := updateTagFile(path, "v1.2.3"); err != nil {
		t.Fatal(err)
	}
	updated, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if got := string(updated); got != "DOMAIN=example.test\nDPP_TAG=v1.2.3\nSECRET=keep\n" {
		t.Fatalf("unexpected env file contents: %q", got)
	}
	info, err := os.Stat(path)
	if err != nil {
		t.Fatal(err)
	}
	if info.Mode().Perm() != 0600 {
		t.Fatalf("expected file mode 0600, got %o", info.Mode().Perm())
	}
}

func TestUpdateTagFileAppendsWhenMissing(t *testing.T) {
	path := filepath.Join(t.TempDir(), ".env")
	if err := os.WriteFile(path, []byte("DOMAIN=example.test\n"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := updateTagFile(path, "v2.0.0"); err != nil {
		t.Fatal(err)
	}
	updated, _ := os.ReadFile(path)
	if !strings.Contains(string(updated), "DPP_TAG=v2.0.0") {
		t.Fatalf("tag missing from env file: %q", updated)
	}
}

func TestHealthEndpoint(t *testing.T) {
	s := &server{}
	recorder := httptest.NewRecorder()
	s.health(recorder, httptest.NewRequest("GET", "/healthz", nil))
	if recorder.Code != 200 || recorder.Body.String() != "ok\n" {
		t.Fatalf("unexpected health response: %d %q", recorder.Code, recorder.Body.String())
	}
}

func TestDeployRejectsUnauthorizedRequest(t *testing.T) {
	s := &server{config: config{token: "secret"}}
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodPost, "/deploy", strings.NewReader(`{"tag":"v1.2.3"}`))
	request.Header.Set("Content-Type", "application/json")
	s.deploy(recorder, request)
	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d", recorder.Code)
	}
}

func TestDeployRejectsInvalidTagBeforeDockerCall(t *testing.T) {
	s := &server{config: config{token: "secret"}}
	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodPost, "/deploy", strings.NewReader(`{"tag":"latest"}`))
	request.Header.Set("Authorization", "Bearer secret")
	request.Header.Set("Content-Type", "application/json")
	s.deploy(recorder, request)
	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", recorder.Code)
	}
}
