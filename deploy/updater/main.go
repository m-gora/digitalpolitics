package main

import (
	"context"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path/filepath"
	"regexp"
	"strings"
	"sync"
	"syscall"
	"time"
)

const (
	defaultSocket    = "/var/run/docker.sock"
	defaultListen    = ":8090"
	defaultProject   = "dpp"
	defaultStateFile = "/deployment/.env"
	appHealthPort    = 8000
)

var (
	semverPattern = regexp.MustCompile(`^v[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$`)
	imagePattern  = regexp.MustCompile(`^ghcr\.io/[a-z0-9][a-z0-9._-]*/[a-z0-9][a-z0-9._-]*$`)
)

type config struct {
	listen       string
	socket       string
	token        string
	image        string
	project      string
	stateFile    string
	registryUser string
	registryPass string
}

type server struct {
	config config
	engine *engine
	mu     sync.Mutex
}

type engine struct {
	client *http.Client
	api    string
}

type listedContainer struct {
	ID    string   `json:"Id"`
	Names []string `json:"Names"`
}

type networkEndpoint struct {
	NetworkID  string         `json:"NetworkID"`
	IPAddress  string         `json:"IPAddress"`
	Aliases    []string       `json:"Aliases"`
	Links      []string       `json:"Links"`
	IPAM       map[string]any `json:"IPAMConfig"`
	DriverOps  map[string]any `json:"DriverOpts"`
	GwPriority int            `json:"GwPriority"`
}

type inspectedContainer struct {
	ID              string         `json:"Id"`
	Name            string         `json:"Name"`
	Config          map[string]any `json:"Config"`
	HostConfig      map[string]any `json:"HostConfig"`
	NetworkSettings struct {
		Networks map[string]networkEndpoint `json:"Networks"`
	} `json:"NetworkSettings"`
}

func main() {
	cfg, err := loadConfig()
	if err != nil {
		log.Fatal(err)
	}

	eng, err := newEngine(cfg.socket)
	if err != nil {
		log.Fatal(err)
	}
	s := &server{config: cfg, engine: eng}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /healthz", s.health)
	mux.HandleFunc("POST /deploy", s.deploy)

	httpServer := &http.Server{
		Addr:              cfg.listen,
		Handler:           mux,
		ReadHeaderTimeout: 5 * time.Second,
		IdleTimeout:       30 * time.Second,
	}

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = httpServer.Shutdown(shutdownCtx)
	}()

	log.Printf("deployment receiver listening on %s", cfg.listen)
	if err := httpServer.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}

func loadConfig() (config, error) {
	cfg := config{
		listen:       envOr("LISTEN_ADDR", defaultListen),
		socket:       envOr("DOCKER_SOCKET", defaultSocket),
		token:        os.Getenv("DEPLOY_TOKEN"),
		image:        strings.TrimSuffix(os.Getenv("DPP_IMAGE"), ":"),
		project:      envOr("COMPOSE_PROJECT", defaultProject),
		stateFile:    envOr("DEPLOY_STATE_FILE", defaultStateFile),
		registryUser: os.Getenv("GHCR_USERNAME"),
		registryPass: os.Getenv("GHCR_TOKEN"),
	}
	if cfg.token == "" {
		return config{}, errors.New("DEPLOY_TOKEN is required")
	}
	if !imagePattern.MatchString(cfg.image) || strings.Contains(cfg.image, "//") || strings.HasSuffix(cfg.image, "/") {
		return config{}, errors.New("DPP_IMAGE must be a lowercase ghcr.io/<owner>/<image> reference without a tag")
	}
	if (cfg.registryUser == "") != (cfg.registryPass == "") {
		return config{}, errors.New("GHCR_USERNAME and GHCR_TOKEN must both be set, or both be empty for a public image")
	}
	if cfg.project == "" || strings.ContainsAny(cfg.project, " /\t\n") {
		return config{}, errors.New("COMPOSE_PROJECT must be a non-empty Compose project name")
	}
	return cfg, nil
}

func envOr(key, fallback string) string {
	if value := os.Getenv(key); value != "" {
		return value
	}
	return fallback
}

func newEngine(socket string) (*engine, error) {
	transport := &http.Transport{
		DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
			return (&net.Dialer{}).DialContext(ctx, "unix", socket)
		},
	}
	client := &http.Client{Transport: transport, Timeout: 15 * time.Minute}
	eng := &engine{client: client}
	body, err := eng.raw(context.Background(), http.MethodGet, "/version", nil, nil)
	if err != nil {
		return nil, fmt.Errorf("connect to Docker Engine: %w", err)
	}
	var version struct {
		APIVersion string `json:"ApiVersion"`
	}
	if err := json.Unmarshal(body, &version); err != nil || !regexp.MustCompile(`^[0-9]+\.[0-9]+$`).MatchString(version.APIVersion) {
		return nil, errors.New("Docker Engine returned an invalid API version")
	}
	eng.api = "/v" + version.APIVersion
	return eng, nil
}

func (e *engine) raw(ctx context.Context, method, path string, body io.Reader, headers map[string]string) ([]byte, error) {
	req, err := http.NewRequestWithContext(ctx, method, "http://docker"+path, body)
	if err != nil {
		return nil, err
	}
	for key, value := range headers {
		req.Header.Set(key, value)
	}
	resp, err := e.client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		return nil, err
	}
	if resp.StatusCode < 200 || resp.StatusCode >= 300 {
		return nil, fmt.Errorf("Docker Engine API %s %s returned %s: %s", method, path, resp.Status, strings.TrimSpace(string(data)))
	}
	return data, nil
}

func (e *engine) request(ctx context.Context, method, path string, body any) ([]byte, error) {
	var reader io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return nil, err
		}
		reader = strings.NewReader(string(encoded))
	}
	headers := map[string]string{}
	if body != nil {
		headers["Content-Type"] = "application/json"
	}
	return e.raw(ctx, method, e.api+path, reader, headers)
}

func (e *engine) pull(ctx context.Context, image, username, password string) error {
	path := e.api + "/images/create?fromImage=" + url.QueryEscape(image)
	headers := map[string]string{}
	if username != "" {
		auth, _ := json.Marshal(map[string]string{
			"username":      username,
			"password":      password,
			"serveraddress": "ghcr.io",
		})
		headers["X-Registry-Auth"] = base64.URLEncoding.EncodeToString(auth)
	}
	data, err := e.raw(ctx, http.MethodPost, path, nil, headers)
	if err != nil {
		return err
	}
	for _, line := range strings.Split(string(data), "\n") {
		var event struct {
			Error       string `json:"error"`
			ErrorDetail struct {
				Message string `json:"message"`
			} `json:"errorDetail"`
		}
		if json.Unmarshal([]byte(line), &event) == nil {
			if event.ErrorDetail.Message != "" {
				return errors.New(event.ErrorDetail.Message)
			}
			if event.Error != "" {
				return errors.New(event.Error)
			}
		}
	}
	return nil
}

func (e *engine) findApp(ctx context.Context, project string) (listedContainer, error) {
	filters, _ := json.Marshal(map[string][]string{"label": {
		"com.docker.compose.project=" + project,
		"com.docker.compose.service=app",
	}})
	path := e.api + "/containers/json?all=1&filters=" + url.QueryEscape(string(filters))
	data, err := e.raw(ctx, http.MethodGet, path, nil, nil)
	if err != nil {
		return listedContainer{}, err
	}
	var found []listedContainer
	if err := json.Unmarshal(data, &found); err != nil {
		return listedContainer{}, err
	}
	if len(found) != 1 {
		return listedContainer{}, fmt.Errorf("expected exactly one Compose app container for project %q, found %d", project, len(found))
	}
	return found[0], nil
}

func (e *engine) inspect(ctx context.Context, id string) (inspectedContainer, error) {
	data, err := e.request(ctx, http.MethodGet, "/containers/"+url.PathEscape(id)+"/json", nil)
	if err != nil {
		return inspectedContainer{}, err
	}
	var result inspectedContainer
	if err := json.Unmarshal(data, &result); err != nil {
		return inspectedContainer{}, err
	}
	return result, nil
}

func (e *engine) create(ctx context.Context, name string, inspected inspectedContainer, image string, command []string, service string, aliasesForService bool) (string, error) {
	config := cloneMap(inspected.Config)
	config["Image"] = image
	if command != nil {
		config["Cmd"] = command
	}
	labels := stringMap(config["Labels"])
	labels["com.docker.compose.service"] = service
	if service != "app" {
		labels["com.docker.compose.oneoff"] = "True"
		labels["com.docker.compose.container-number"] = "1"
		delete(labels, "com.docker.compose.config-hash")
	}
	config["Labels"] = labels

	hostConfig := cloneMap(inspected.HostConfig)
	hostConfig["AutoRemove"] = false
	if service != "app" {
		hostConfig["RestartPolicy"] = map[string]any{"Name": "no"}
	}

	endpoints := map[string]any{}
	for networkName, endpoint := range inspected.NetworkSettings.Networks {
		entry := map[string]any{}
		aliases := append([]string(nil), endpoint.Aliases...)
		if !aliasesForService {
			aliases = []string{"migration"}
		}
		if len(aliases) > 0 {
			entry["Aliases"] = aliases
		}
		if len(endpoint.Links) > 0 {
			entry["Links"] = endpoint.Links
		}
		if len(endpoint.IPAM) > 0 && aliasesForService {
			entry["IPAMConfig"] = endpoint.IPAM
		}
		if len(endpoint.DriverOps) > 0 {
			entry["DriverOpts"] = endpoint.DriverOps
		}
		if endpoint.GwPriority != 0 {
			entry["GwPriority"] = endpoint.GwPriority
		}
		endpoints[networkName] = entry
	}

	body := cloneMap(config)
	body["HostConfig"] = hostConfig
	body["NetworkingConfig"] = map[string]any{"EndpointsConfig": endpoints}
	data, err := e.request(ctx, http.MethodPost, "/containers/create?name="+url.QueryEscape(name), body)
	if err != nil {
		return "", err
	}
	var created struct {
		ID string `json:"Id"`
	}
	if err := json.Unmarshal(data, &created); err != nil {
		return "", err
	}
	if created.ID == "" {
		return "", errors.New("Docker Engine created a container without returning its ID")
	}
	return created.ID, nil
}

func (e *engine) start(ctx context.Context, id string) error {
	_, err := e.request(ctx, http.MethodPost, "/containers/"+url.PathEscape(id)+"/start", nil)
	return err
}

func (e *engine) stop(ctx context.Context, id string) error {
	_, err := e.request(ctx, http.MethodPost, "/containers/"+url.PathEscape(id)+"/stop?t=10", nil)
	return err
}

func (e *engine) remove(ctx context.Context, id string) error {
	_, err := e.request(ctx, http.MethodDelete, "/containers/"+url.PathEscape(id)+"?force=true&v=false", nil)
	return err
}

func (e *engine) rename(ctx context.Context, id, name string) error {
	_, err := e.request(ctx, http.MethodPost, "/containers/"+url.PathEscape(id)+"/rename?name="+url.QueryEscape(strings.TrimPrefix(name, "/")), nil)
	return err
}

func (e *engine) disconnect(ctx context.Context, networkID, containerID string) error {
	_, err := e.request(ctx, http.MethodPost, "/networks/"+url.PathEscape(networkID)+"/disconnect", map[string]any{
		"Container": containerID,
		"Force":     true,
	})
	return err
}

func (e *engine) connect(ctx context.Context, networkID, containerID string, endpoint networkEndpoint, aliases []string) error {
	endpointConfig := map[string]any{}
	if len(aliases) > 0 {
		endpointConfig["Aliases"] = aliases
	}
	if len(endpoint.IPAM) > 0 {
		endpointConfig["IPAMConfig"] = endpoint.IPAM
	}
	if len(endpoint.DriverOps) > 0 {
		endpointConfig["DriverOpts"] = endpoint.DriverOps
	}
	_, err := e.request(ctx, http.MethodPost, "/networks/"+url.PathEscape(networkID)+"/connect", map[string]any{
		"Container":      containerID,
		"EndpointConfig": endpointConfig,
	})
	return err
}

func (e *engine) reconnectNetworks(ctx context.Context, containerID string, networks map[string]networkEndpoint) error {
	container, err := e.inspect(ctx, containerID)
	if err != nil {
		return err
	}
	for name, endpoint := range networks {
		if endpoint.NetworkID == "" {
			continue
		}
		if existing, ok := container.NetworkSettings.Networks[name]; ok && existing.NetworkID == endpoint.NetworkID {
			continue
		}
		if err := e.connect(ctx, endpoint.NetworkID, containerID, endpoint, endpoint.Aliases); err != nil {
			return err
		}
	}
	return nil
}

func (e *engine) wait(ctx context.Context, id string) (int64, error) {
	data, err := e.request(ctx, http.MethodPost, "/containers/"+url.PathEscape(id)+"/wait?condition=not-running", nil)
	if err != nil {
		return -1, err
	}
	var result struct {
		StatusCode int64 `json:"StatusCode"`
		Error      any   `json:"Error"`
	}
	if err := json.Unmarshal(data, &result); err != nil {
		return -1, err
	}
	return result.StatusCode, nil
}

func (e *engine) logs(ctx context.Context, id string) (string, error) {
	data, err := e.request(ctx, http.MethodGet, "/containers/"+url.PathEscape(id)+"/logs?stdout=1&stderr=1&timestamps=0", nil)
	if err != nil {
		return "", err
	}
	return string(demux(data)), nil
}

func (e *engine) appIP(ctx context.Context, id string) (string, error) {
	container, err := e.inspect(ctx, id)
	if err != nil {
		return "", err
	}
	for _, network := range container.NetworkSettings.Networks {
		if network.IPAddress != "" {
			return network.IPAddress, nil
		}
	}
	return "", errors.New("replacement app has no IPv4 address")
}

func (s *server) health(w http.ResponseWriter, _ *http.Request) {
	w.WriteHeader(http.StatusOK)
	_, _ = io.WriteString(w, "ok\n")
}

func (s *server) deploy(w http.ResponseWriter, r *http.Request) {
	if !authorized(r.Header.Get("Authorization"), s.config.token) {
		http.Error(w, "unauthorized", http.StatusUnauthorized)
		return
	}
	if !strings.HasPrefix(strings.ToLower(r.Header.Get("Content-Type")), "application/json") {
		http.Error(w, "Content-Type must be application/json", http.StatusUnsupportedMediaType)
		return
	}
	r.Body = http.MaxBytesReader(w, r.Body, 4096)
	var request struct {
		Tag string `json:"tag"`
	}
	decoder := json.NewDecoder(r.Body)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&request); err != nil || !semverPattern.MatchString(request.Tag) {
		http.Error(w, "body must contain a valid v-prefixed SemVer tag", http.StatusBadRequest)
		return
	}
	var extra any
	if err := decoder.Decode(&extra); !errors.Is(err, io.EOF) {
		http.Error(w, "request must contain one JSON object", http.StatusBadRequest)
		return
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	ctx, cancel := context.WithTimeout(context.Background(), 14*time.Minute)
	defer cancel()
	if err := s.perform(ctx, request.Tag); err != nil {
		log.Printf("deployment %s failed: %v", request.Tag, err)
		http.Error(w, "deployment failed; see updater logs", http.StatusInternalServerError)
		return
	}
	log.Printf("deployment %s completed", request.Tag)
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(map[string]string{"status": "deployed", "tag": request.Tag})
}

func (s *server) perform(ctx context.Context, tag string) error {
	image := s.config.image + ":" + tag
	if err := s.engine.pull(ctx, image, s.config.registryUser, s.config.registryPass); err != nil {
		return fmt.Errorf("pull %s: %w", image, err)
	}

	listed, err := s.engine.findApp(ctx, s.config.project)
	if err != nil {
		return err
	}
	old, err := s.engine.inspect(ctx, listed.ID)
	if err != nil {
		return err
	}
	if len(old.NetworkSettings.Networks) == 0 {
		return errors.New("app container has no attached networks")
	}

	if err := s.runMigration(ctx, old, image, tag); err != nil {
		return fmt.Errorf("database migration failed: %w", err)
	}
	return s.replaceApp(ctx, listed, old, image, tag)
}

func (s *server) runMigration(ctx context.Context, app inspectedContainer, image, tag string) error {
	name := "dpp-migration-" + strings.ReplaceAll(tag, ".", "-") + "-" + fmt.Sprint(time.Now().UnixNano())
	id, err := s.engine.create(ctx, name, app, image, []string{"alembic", "upgrade", "head"}, "migration", false)
	if err != nil {
		return fmt.Errorf("create migration container: %w", err)
	}
	defer func() { _ = s.engine.remove(context.Background(), id) }()
	if err := s.engine.start(ctx, id); err != nil {
		return fmt.Errorf("start migration container: %w", err)
	}
	status, err := s.engine.wait(ctx, id)
	if err != nil {
		return fmt.Errorf("wait for migration: %w", err)
	}
	if status != 0 {
		logs, _ := s.engine.logs(ctx, id)
		return fmt.Errorf("migration exited with status %d: %s", status, strings.TrimSpace(logs))
	}
	return nil
}

func (s *server) replaceApp(ctx context.Context, listed listedContainer, old inspectedContainer, image, tag string) error {
	originalName := strings.TrimPrefix(old.Name, "/")
	backupName := originalName + "-rollback-" + fmt.Sprint(time.Now().Unix())
	if err := s.engine.stop(ctx, listed.ID); err != nil {
		_ = s.engine.start(context.Background(), listed.ID)
		return fmt.Errorf("stop old app container: %w", err)
	}
	if err := s.engine.rename(ctx, listed.ID, backupName); err != nil {
		_ = s.engine.start(context.Background(), listed.ID)
		return fmt.Errorf("reserve old app container for rollback: %w", err)
	}

	for _, endpoint := range old.NetworkSettings.Networks {
		if endpoint.NetworkID != "" {
			if err := s.engine.disconnect(ctx, endpoint.NetworkID, listed.ID); err != nil {
				return s.rollbackAfterFailure(ctx, listed.ID, backupName, originalName, old.NetworkSettings.Networks, "", fmt.Errorf("disconnect old app from network: %w", err))
			}
		}
	}

	newID, err := s.engine.create(ctx, originalName, old, image, nil, "app", true)
	if err != nil {
		return s.rollbackAfterFailure(ctx, listed.ID, backupName, originalName, old.NetworkSettings.Networks, "", fmt.Errorf("create replacement app: %w", err))
	}
	if err := s.engine.start(ctx, newID); err != nil {
		return s.rollbackAfterFailure(ctx, listed.ID, backupName, originalName, old.NetworkSettings.Networks, newID, fmt.Errorf("start replacement app: %w", err))
	}
	if err := s.waitHealthy(ctx, newID); err != nil {
		return s.rollbackAfterFailure(ctx, listed.ID, backupName, originalName, old.NetworkSettings.Networks, newID, fmt.Errorf("replacement app did not become healthy: %w", err))
	}
	if err := updateTagFile(s.config.stateFile, tag); err != nil {
		return s.rollbackAfterFailure(ctx, listed.ID, backupName, originalName, old.NetworkSettings.Networks, newID, fmt.Errorf("persist DPP_TAG: %w", err))
	}
	if err := s.engine.remove(ctx, listed.ID); err != nil {
		log.Printf("warning: new app is healthy but old container cleanup failed: %v", err)
	}
	return nil
}

func (s *server) rollback(ctx context.Context, oldID, backupName, originalName string, networks map[string]networkEndpoint, newID string) error {
	if newID != "" {
		_ = s.engine.stop(ctx, newID)
		_ = s.engine.remove(ctx, newID)
	}
	if err := s.engine.rename(ctx, oldID, originalName); err != nil {
		return fmt.Errorf("rename old app back from %s: %w", backupName, err)
	}
	if err := s.engine.reconnectNetworks(ctx, oldID, networks); err != nil {
		return fmt.Errorf("reconnect old app: %w", err)
	}
	if err := s.engine.start(ctx, oldID); err != nil {
		return fmt.Errorf("restart old app: %w", err)
	}
	return nil
}

func (s *server) rollbackAfterFailure(ctx context.Context, oldID, backupName, originalName string, networks map[string]networkEndpoint, newID string, cause error) error {
	if err := s.rollback(ctx, oldID, backupName, originalName, networks, newID); err != nil {
		return fmt.Errorf("%w (rollback also failed: %v)", cause, err)
	}
	return cause
}

func (s *server) waitHealthy(ctx context.Context, id string) error {
	deadline := time.NewTimer(90 * time.Second)
	defer deadline.Stop()
	ticker := time.NewTicker(time.Second)
	defer ticker.Stop()
	client := &http.Client{Timeout: 2 * time.Second}
	var lastErr error
	for {
		ip, err := s.engine.appIP(ctx, id)
		if err == nil {
			request, _ := http.NewRequestWithContext(ctx, http.MethodGet, fmt.Sprintf("http://%s:%d/healthz", ip, appHealthPort), nil)
			response, requestErr := client.Do(request)
			if requestErr == nil {
				_ = response.Body.Close()
				if response.StatusCode == http.StatusOK {
					return nil
				}
				lastErr = fmt.Errorf("health endpoint returned %s", response.Status)
			} else {
				lastErr = requestErr
			}
		} else {
			lastErr = err
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-deadline.C:
			return lastErr
		case <-ticker.C:
		}
	}
}

func authorized(header, token string) bool {
	const prefix = "Bearer "
	if !strings.HasPrefix(header, prefix) {
		return false
	}
	provided := strings.TrimPrefix(header, prefix)
	return len(provided) == len(token) && subtle.ConstantTimeCompare([]byte(provided), []byte(token)) == 1
}

func updateTagFile(path, tag string) error {
	data, err := os.ReadFile(path)
	if err != nil {
		return err
	}
	mode := os.FileMode(0600)
	if info, statErr := os.Stat(path); statErr == nil {
		mode = info.Mode().Perm()
	}
	text := string(data)
	lines := strings.Split(text, "\n")
	found := false
	for i, line := range lines {
		if strings.TrimSpace(strings.SplitN(line, "=", 2)[0]) == "DPP_TAG" {
			lines[i] = "DPP_TAG=" + tag
			found = true
		}
	}
	if !found {
		if len(lines) > 0 && lines[len(lines)-1] == "" {
			lines = append(lines[:len(lines)-1], "DPP_TAG="+tag, "")
		} else {
			lines = append(lines, "DPP_TAG="+tag)
		}
	}
	updated := []byte(strings.Join(lines, "\n"))
	dir := filepath.Dir(path)
	tmp, err := os.CreateTemp(dir, ".dpp-env-*")
	if err != nil {
		return err
	}
	tmpName := tmp.Name()
	defer os.Remove(tmpName)
	if err := tmp.Chmod(mode); err != nil {
		_ = tmp.Close()
		return err
	}
	if _, err := tmp.Write(updated); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Sync(); err != nil {
		_ = tmp.Close()
		return err
	}
	if err := tmp.Close(); err != nil {
		return err
	}
	return os.Rename(tmpName, path)
}

func cloneMap(source map[string]any) map[string]any {
	clone := make(map[string]any, len(source))
	for key, value := range source {
		clone[key] = value
	}
	return clone
}

func stringMap(value any) map[string]string {
	result := map[string]string{}
	if labels, ok := value.(map[string]any); ok {
		for key, value := range labels {
			if text, ok := value.(string); ok {
				result[key] = text
			}
		}
	}
	return result
}

func demux(data []byte) []byte {
	var result []byte
	for len(data) >= 8 {
		length := int(data[4])<<24 | int(data[5])<<16 | int(data[6])<<8 | int(data[7])
		if length < 0 || len(data) < 8+length {
			return data
		}
		result = append(result, data[8:8+length]...)
		data = data[8+length:]
	}
	if len(data) > 0 {
		return append(result, data...)
	}
	return result
}
