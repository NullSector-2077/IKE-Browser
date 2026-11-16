//! I.K.E. AdBlock Engine.
//!
//! A small Python module around the adblock-rust engine (MPL-2.0,
//! https://github.com/brave/adblock-rust), built and shipped by I.K.E. itself so
//! that the browser does not depend on any other browser or on an outdated
//! binding. The Python side lives in `vendor/adblock/__init__.py`.

use std::collections::{HashMap, HashSet};
use std::fs;
use std::panic::{catch_unwind, AssertUnwindSafe};

use adblock::lists::{FilterFormat, FilterSet as AFilterSet, ParseOptions, RuleTypes};
use adblock::request::Request as ARequest;
use adblock::resources::{MimeType, PermissionMask, Resource, ResourceType};
use adblock::Engine as AEngine;
use pyo3::exceptions::{PyIOError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyBytes;

/// Version of the adblock-rust engine this module was built with.
const ENGINE_VERSION: &str = "0.13.5";

/// Run a call into the filter engine and turn a panic inside it into an
/// error value. The engine reads addresses chosen by web pages and lists
/// downloaded from the network: a fault there must end as "this request could
/// not be checked" (the browser then lets it through and counts the error),
/// never as the end of the whole browser.
fn guarded<T>(what: &str, call: impl FnOnce() -> T) -> Result<T, String> {
    catch_unwind(AssertUnwindSafe(call)).map_err(|cause| {
        let detail = cause
            .downcast_ref::<&str>()
            .map(|s| s.to_string())
            .or_else(|| cause.downcast_ref::<String>().cloned())
            .unwrap_or_else(|| "unknown cause".to_string());
        format!("the filter engine failed in {what}: {detail}")
    })
}

fn guarded_py<T>(what: &str, call: impl FnOnce() -> T) -> PyResult<T> {
    guarded(what, call).map_err(PyRuntimeError::new_err)
}

/// A set of filter lists, to build an Engine from.
#[pyclass(module = "ike_adblock")]
struct FilterSet {
    inner: AFilterSet,
}

#[pymethods]
impl FilterSet {
    #[new]
    #[pyo3(signature = (debug = false))]
    fn new(debug: bool) -> Self {
        FilterSet { inner: AFilterSet::new(debug) }
    }

    /// Add the text of a filter list. `format` is "standard" (ABP/uBlock
    /// syntax) or "hosts"; `rule_types` is "all", "network" or "cosmetic";
    /// `trusted` lets the list use rules reserved for trusted sources.
    #[pyo3(signature = (filter_list, format = "standard", include_redirect_urls = false, rule_types = "all", trusted = false))]
    fn add_filter_list(
        &mut self,
        filter_list: &str,
        format: &str,
        include_redirect_urls: bool,
        rule_types: &str,
        trusted: bool,
    ) -> PyResult<()> {
        let _ = include_redirect_urls; // accepted for compatibility with older bindings
        let format = match format {
            "standard" => FilterFormat::Standard,
            "hosts" => FilterFormat::Hosts,
            other => return Err(PyValueError::new_err(format!("unknown filter format: {other}"))),
        };
        let rule_types = match rule_types {
            "all" => RuleTypes::All,
            "network" | "networkonly" => RuleTypes::NetworkOnly,
            "cosmetic" | "cosmeticonly" => RuleTypes::CosmeticOnly,
            other => return Err(PyValueError::new_err(format!("unknown rule types: {other}"))),
        };
        let permissions = if trusted { PermissionMask::from_bits(1) } else { PermissionMask::default() };
        let opts = ParseOptions { format, rule_types, permissions };
        let inner = &mut self.inner;
        guarded_py("add_filter_list", move || {
            inner.add_filter_list(filter_list.to_string(), opts);
        })
    }
}

/// What to do with one network request.
#[pyclass(module = "ike_adblock", get_all)]
struct BlockerResult {
    /// A blocking rule matched (an exception may still allow the request).
    matched: bool,
    /// An "important" rule matched: exceptions do not apply.
    important: bool,
    /// Replacement to load instead of the request (a data: URL), if any.
    redirect: Option<String>,
    /// The URL with tracking parameters removed, if a rule removed any.
    rewritten_url: Option<String>,
    /// The exception rule that allows the request, if any.
    exception: Option<String>,
    /// The blocking rule that matched, if any.
    filter: Option<String>,
    /// Why the request could not be checked, if it could not.
    error: Option<String>,
}

#[pymethods]
impl BlockerResult {
    /// True when the request has to be blocked.
    #[getter]
    fn should_block(&self) -> bool {
        self.matched && (self.important || self.exception.is_none())
    }

    fn __repr__(&self) -> String {
        format!(
            "BlockerResult(matched={}, important={}, redirect={:?}, rewritten_url={:?}, exception={:?})",
            self.matched, self.important, self.redirect, self.rewritten_url, self.exception
        )
    }
}

impl BlockerResult {
    fn failed(reason: &str) -> Self {
        BlockerResult {
            matched: false,
            important: false,
            redirect: None,
            rewritten_url: None,
            exception: None,
            filter: None,
            error: Some(reason.to_string()),
        }
    }
}

/// One network request: address, address of the page it belongs to, kind
/// ("script", "image", "xmlhttprequest", ...) and HTTP method.
#[pyclass(module = "ike_adblock", get_all)]
#[derive(Clone)]
struct Request {
    url: String,
    source_url: String,
    request_type: String,
    method: String,
}

#[pymethods]
impl Request {
    #[new]
    #[pyo3(signature = (url, source_url, request_type, method = "GET"))]
    fn new(url: &str, source_url: &str, request_type: &str, method: &str) -> Self {
        Request {
            url: url.to_string(),
            source_url: source_url.to_string(),
            request_type: request_type.to_string(),
            method: method.to_string(),
        }
    }
}

/// What a page needs for cosmetic filtering.
#[pyclass(module = "ike_adblock", get_all)]
struct UrlSpecificResources {
    /// Selectors of elements to hide.
    hide_selectors: HashSet<String>,
    /// Selector -> CSS declarations to apply (":style(...)" rules).
    style_selectors: HashMap<String, Vec<String>>,
    /// Every other cosmetic action, as JSON (procedural filters).
    procedural_actions: Vec<String>,
    /// Selectors that generic rules must not hide on this page.
    exceptions: HashSet<String>,
    /// Scriptlets to run in the page, when resources are loaded.
    injected_script: String,
    /// Generic hiding is switched off for this page.
    generichide: bool,
}

/// The filter engine.
#[pyclass(module = "ike_adblock")]
struct Engine {
    inner: AEngine,
    resources: Vec<Resource>,
}

#[pymethods]
impl Engine {
    #[new]
    #[pyo3(signature = (filter_set, optimize = true))]
    fn new(filter_set: &FilterSet, optimize: bool) -> PyResult<Self> {
        let inner = guarded_py("Engine", || {
            let set = filter_set.inner.clone();
            if optimize {
                AEngine::new_with_filter_set(set)
            } else {
                AEngine::new_with_filter_set_no_optimize(set)
            }
        })?;
        Ok(Engine { inner, resources: Vec::new() })
    }

    /// Check a request given as separate values.
    #[pyo3(signature = (url, source_url, request_type, method = "GET"))]
    fn check_network_urls(&self, py: Python<'_>, url: &str, source_url: &str, request_type: &str, method: &str) -> BlockerResult {
        let checked = guarded("check_network_request", || {
            let request = ARequest::new(url, source_url, request_type, method).map_err(|e| format!("{e:?}"))?;
            Ok::<_, String>(py.detach(|| self.inner.check_network_request(&request)))
        });
        let result = match checked {
            Ok(Ok(result)) => result,
            Ok(Err(reason)) | Err(reason) => return BlockerResult::failed(&reason),
        };
        BlockerResult {
            matched: result.filter.is_some(),
            important: result.important,
            redirect: result.redirect,
            rewritten_url: result.rewritten_url,
            exception: result.exception.map(|e| e.raw_line.unwrap_or_else(|| "exception".to_string())),
            filter: result.filter.map(|f| f.raw_line.unwrap_or_else(|| "filter".to_string())),
            error: None,
        }
    }

    /// Check a Request object.
    fn check_network_request(&self, py: Python<'_>, request: &Request) -> BlockerResult {
        self.check_network_urls(py, &request.url, &request.source_url, &request.request_type, &request.method)
    }

    /// Content-Security-Policy directives that list rules add to a document.
    #[pyo3(signature = (url, source_url, request_type = "document"))]
    fn get_csp_directives(&self, url: &str, source_url: &str, request_type: &str) -> Option<String> {
        guarded("get_csp_directives", || {
            let request = ARequest::new(url, source_url, request_type, "GET").ok()?;
            self.inner.get_csp_directives(&request)
        })
        .ok()
        .flatten()
    }

    /// Cosmetic resources of a page.
    fn url_cosmetic_resources(&self, url: &str) -> PyResult<UrlSpecificResources> {
        guarded_py("url_cosmetic_resources", || self.cosmetic_resources(url))
    }

    /// Generic hiding selectors needed for the classes and ids found in a page.
    fn hidden_class_id_selectors(&self, classes: Vec<String>, ids: Vec<String>, exceptions: HashSet<String>) -> PyResult<Vec<String>> {
        guarded_py("hidden_class_id_selectors", || {
            self.inner.hidden_class_id_selectors(classes.iter(), ids.iter(), &exceptions)
        })
    }
    /// Register a resource for "$redirect=" rules or scriptlets. `content` is
    /// base64; `content_type` is a MIME type, or "template" for a scriptlet.
    #[pyo3(signature = (name, content_type, content, aliases = None))]
    fn add_resource(&mut self, name: &str, content_type: &str, content: &str, aliases: Option<Vec<String>>) -> PyResult<()> {
        let kind = if content_type == "template" {
            ResourceType::Template
        } else {
            ResourceType::Mime(MimeType::from(content_type))
        };
        self.resources.retain(|r| r.name != name);
        self.resources.push(Resource {
            name: name.to_string(),
            aliases: aliases.unwrap_or_default(),
            kind,
            content: content.to_string(),
            dependencies: Vec::new(),
            permission: PermissionMask::default(),
        });
        let (inner, resources) = (&mut self.inner, self.resources.clone());
        guarded_py("add_resource", move || inner.use_resources(resources))
    }

    /// The compiled engine as bytes (resources are not included).
    fn serialize<'py>(&self, py: Python<'py>) -> PyResult<Bound<'py, PyBytes>> {
        let data = guarded_py("serialize", || self.inner.serialize())?;
        Ok(PyBytes::new(py, &data))
    }

    fn deserialize(&mut self, data: &[u8]) -> PyResult<()> {
        let inner = &mut self.inner;
        guarded_py("deserialize", move || inner.deserialize(data))?
            .map_err(|e| PyValueError::new_err(format!("cannot read the engine data: {e:?}")))
    }

    fn serialize_to_file(&self, path: &str) -> PyResult<()> {
        let data = guarded_py("serialize", || self.inner.serialize())?;
        fs::write(path, data).map_err(|e| PyIOError::new_err(e.to_string()))
    }

    fn deserialize_from_file(&mut self, path: &str) -> PyResult<()> {
        let data = fs::read(path).map_err(|e| PyIOError::new_err(e.to_string()))?;
        self.deserialize(&data)
    }
}

impl Engine {
    fn cosmetic_resources(&self, url: &str) -> UrlSpecificResources {
        let res = self.inner.url_cosmetic_resources(url);
        let mut style_selectors: HashMap<String, Vec<String>> = HashMap::new();
        let mut procedural_actions = Vec::new();
        for raw in res.procedural_actions {
            // {"selector":[{"type":"css-selector","arg":".x"}],"action":{"type":"style","arg":"..."}}
            let mut plain_style = None;
            if let Ok(serde_json::Value::Object(obj)) = serde_json::from_str::<serde_json::Value>(&raw) {
                let selector = obj.get("selector").and_then(|s| s.as_array());
                let action = obj.get("action").and_then(|a| a.as_object());
                if let (Some(selector), Some(action)) = (selector, action) {
                    if selector.len() == 1
                        && selector[0].get("type").and_then(|t| t.as_str()) == Some("css-selector")
                        && action.get("type").and_then(|t| t.as_str()) == Some("style")
                    {
                        let sel = selector[0].get("arg").and_then(|a| a.as_str());
                        let style = action.get("arg").and_then(|a| a.as_str());
                        if let (Some(sel), Some(style)) = (sel, style) {
                            plain_style = Some((sel.to_string(), style.to_string()));
                        }
                    }
                }
            }
            match plain_style {
                Some((sel, style)) => style_selectors.entry(sel).or_default().push(style),
                None => procedural_actions.push(raw),
            }
        }
        UrlSpecificResources {
            hide_selectors: res.hide_selectors,
            style_selectors,
            procedural_actions,
            exceptions: res.exceptions,
            injected_script: res.injected_script,
            generichide: res.generichide,
        }
    }
}

#[pymodule]
fn ike_adblock(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<FilterSet>()?;
    m.add_class::<Engine>()?;
    m.add_class::<Request>()?;
    m.add_class::<BlockerResult>()?;
    m.add_class::<UrlSpecificResources>()?;
    m.add("__version__", env!("CARGO_PKG_VERSION"))?;
    m.add("ENGINE_VERSION", ENGINE_VERSION)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::guarded;

    #[test]
    fn a_panic_becomes_an_error() {
        let failed: Result<u32, String> = guarded("test", || panic!("boom {}", 7));
        let reason = failed.unwrap_err();
        assert!(reason.contains("test") && reason.contains("boom 7"), "{reason}");
        let failed: Result<u32, String> = guarded("slice", || {
            let empty: Vec<u32> = Vec::new();
            empty[3]
        });
        assert!(failed.unwrap_err().contains("slice"));
        // a call that works is not touched, and the next call works after a failure
        assert_eq!(guarded("fine", || 41 + 1), Ok(42));
    }
}
