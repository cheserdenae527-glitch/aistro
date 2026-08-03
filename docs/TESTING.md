# 测试与性能分析

## 安装依赖

```powershell
python -m pip install -r backend/requirements-dev.txt
cd frontend
npm install
npx playwright install chromium
```

运行期性能分析（py-spy、Locust）额外安装：

```powershell
python -m pip install -r backend/requirements-perf.txt
```

## 一键测试

```powershell
.\scripts\run_tests.ps1
```

只跑单元/组件测试、不启动浏览器：

```powershell
.\scripts\run_tests.ps1 -SkipE2E
```

带后端覆盖率：

```powershell
.\scripts\run_tests.ps1 -Coverage
```

等价的手动命令：

```powershell
cd backend
python -m pytest --cov=app --cov-report=term-missing
cd ..\frontend
npm test
npm run e2e
```

## 性能分析

一键产出微基准和 cProfile 文件：

```powershell
.\scripts\run_perf.ps1
```

查看基准结果：

```powershell
python -m pytest backend/benchmarks/test_benchmark.py --benchmark-only --benchmark-json reports/benchmark.json
```

查看 cProfile：

```powershell
python -m pstats reports/profile.out
```

分析已经运行的 Python 进程（需要 py-spy）：

```powershell
py-spy record --pid <backend-pid> -o reports/flamegraph.svg
```

接口压测（需要后端已启动）：

```powershell
cd backend
locust -f locustfile.py --host http://localhost:8000
```
