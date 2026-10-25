// Package headless_browser provides the small upstream browser facade using managed Chromium.
// Local adaptation: no fingerprint modifications, third-party browser downloads, or sandbox bypass.
package headless_browser

import (
	"encoding/json"
	"github.com/go-rod/rod"
	"github.com/go-rod/rod/lib/launcher"
	"github.com/go-rod/rod/lib/proto"
	"os"
)

type config struct {
	headless bool
	bin      string
	cookies  string
	proxy    string
}
type Option func(*config)
type Browser struct {
	*rod.Browser
	directory string
}

func WithHeadless(v bool) Option        { return func(c *config) { c.headless = v } }
func WithChromeBinPath(v string) Option { return func(c *config) { c.bin = v } }
func WithCookies(v string) Option       { return func(c *config) { c.cookies = v } }
func WithProxy(v string) Option         { return func(c *config) { c.proxy = v } }

// Retained for upstream CLI source compatibility; intentionally have no effect.
func WithFingerprint(v string) Option           { return func(c *config) {} }
func WithFingerprintSeed(v int) Option          { return func(c *config) {} }
func WithStealthJS(v bool) Option               { return func(c *config) {} }
func WithLanguage(v string) Option              { return func(c *config) {} }
func WithExtraFlags(v map[string]string) Option { return func(c *config) {} }
func New(options ...Option) *Browser {
	c := &config{headless: true}
	for _, o := range options {
		o(c)
	}
	if c.bin == "" {
		panic("Managed Chromium path is required")
	}
	dir, err := os.MkdirTemp("", "xhs-profile-")
	if err != nil {
		panic(err)
	}
	l := launcher.New().Bin(c.bin).Headless(c.headless).NoSandbox(false).UserDataDir(dir).Set("disable-dev-shm-usage")
	if c.proxy != "" {
		l = l.Proxy(c.proxy)
	}
	endpoint, err := l.Launch()
	if err != nil {
		os.RemoveAll(dir)
		panic(err)
	}
	b := rod.New().ControlURL(endpoint).MustConnect()
	if c.cookies != "" {
		var cookies []*proto.NetworkCookieParam
		if json.Unmarshal([]byte(c.cookies), &cookies) == nil && len(cookies) > 0 {
			if err = b.SetCookies(cookies); err != nil {
				b.Close()
				os.RemoveAll(dir)
				panic(err)
			}
		}
	}
	return &Browser{Browser: b, directory: dir}
}
func (b *Browser) NewPage() *rod.Page { return b.Browser.MustPage() }
func (b *Browser) Close() error       { err := b.Browser.Close(); os.RemoveAll(b.directory); return err }
