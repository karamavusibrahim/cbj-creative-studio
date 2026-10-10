using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.SceneManagement;

public class GameManager : MonoBehaviour
{
    public static GameManager Instance { get; private set; }

    private IGridManager gridManager;
    public IGridManager GridManager => gridManager;
    
    [Header("Grid Settings")]
    [SerializeField] private GameObject cellPrefab;
    [SerializeField] private float cellSpacing;
    [SerializeField] private ItemFactory itemFactory;
    [SerializeField] private GameObject exitParticlePrefab;
    
    [Header("Border Prefabs")]
    [SerializeField] private GameObject borderPrefab;
    [SerializeField] private GameObject cornerPrefab;
    [SerializeField] private GameObject exitPrefab;
    
    [Header("Border Scale Settings")]
    [Tooltip("Base scale X value for 1 cell (will be multiplied by cell count)")]
    [SerializeField] private float borderBaseScalePerCell = 12.3f;
    [SerializeField] private float borderScaleY = 60.54f;
    [SerializeField] private float borderScaleZ = 100f;
    
    [Header("Border Position Settings")]
    [SerializeField] private float borderOffset = 0.6f;
    [SerializeField] private float borderYPosition = 0.27f;
    
    [Header("Corner Settings")]
    [SerializeField] private Vector3 cornerScale = new Vector3(0.2f, 0.2f, 0.2f);
    [SerializeField] private float cornerYOffset = 0f;
    [SerializeField] private float cornerOutwardOffset = 0.6f;
    [SerializeField] private Vector3 cornerBaseRotation = Vector3.zero;
    
    [Header("Exit Scale Settings")]
    [Tooltip("Base scale X value for 1 cell exit (will be multiplied by cell count)")]
    [SerializeField] private float exitBaseScalePerCell = 12.3f;
    [SerializeField] private float exitScaleY = 60.54f;
    [SerializeField] private float exitScaleZ = 100f;
    [Tooltip("Name of arrow child object in exit prefab")]
    [SerializeField] private string exitArrowChildName = "ExitArrow";
    [SerializeField] private Vector3 exitArrowScale = Vector3.one;

    [Header("Clip Settings")]
    [SerializeField] public float clipPadding = 0.15f;

    [Header("Level Loading")]
    [SerializeField] private float blockYScaleMultiplier = 1f;
    [SerializeField] private float blockYOffset = 0f;
    
    [SerializeField] private bool useLevelManager = true;
    
    public LevelData placeHolderLevelData;

    public float exitSpeedPerCell;
    public AnimationCurve blockExitAnimationCurve;
    
    [Header("Exit Animation Settings")]
    public float exitGoDownDepth = 0.2f;
    public float exitRecoveryDuration = 0.3f;
    public AnimationCurve exitRecoveryCurver;
    
    private Transform gridParent;
    private List<GameObject> spawnedBlocks = new List<GameObject>();

    private float remainingTime;
    private bool isTimerRunning;
    private bool hasGameStarted;
    // cbj-creative patch: blocks whose exit slide has started, and whether the win or the fail
    // screen has been shown. Stops the game from showing "Out of Time!" and then "Level Completed".
    private readonly HashSet<GameObject> leavingBlocks = new HashSet<GameObject>();
    private bool isLevelOver;
    public bool IsLevelOver => isLevelOver;
    
    public float pOffsetMultiplier;
    public float pYOffset;
    public float exitParticleTiltAngle;


    public List<Color> gridColors = new List<Color>();
    
    // Public getters for GridManager
    public GameObject BorderPrefab => borderPrefab;
    public GameObject CornerPrefab => cornerPrefab;
    public GameObject ExitPrefab => exitPrefab;
    public float BorderBaseScalePerCell => borderBaseScalePerCell;
    public float BorderScaleY => borderScaleY;
    public float BorderScaleZ => borderScaleZ;
    public float BorderOffset => borderOffset;
    public float BorderYPosition => borderYPosition;
    public Vector3 CornerScale => cornerScale;
    public float CornerYOffset => cornerYOffset;
    public float CornerOutwardOffset => cornerOutwardOffset;
    public Vector3 CornerBaseRotation => cornerBaseRotation;
    public float ExitBaseScalePerCell => exitBaseScalePerCell;
    public float ExitScaleY => exitScaleY;
    public float ExitScaleZ => exitScaleZ;
    public string ExitArrowChildName => exitArrowChildName;
    public Vector3 ExitArrowScale => exitArrowScale;

    public System.Action OnBoardGenerated;
    public System.Action OnBoardCleared;
    public System.Action OnGameStarted;


    public GameObject exitArrowPrefab;
    public float exitArrowY0ffset;
    
    
    
    // Board dimensions for camera fitting
    public Vector3 GetBoardCenter()
    {
        if (gridManager == null) return Vector3.zero;
        float totalWidth = (gridManager.GridWidth - 1) * cellSpacing;
        float totalHeight = (gridManager.GridHeight - 1) * cellSpacing;
        return gridManager.GridOrigin + new Vector3(totalWidth * 0.5f, 0, totalHeight * 0.5f);
    }
    
    public Vector2 GetBoardSize()
    {
        if (gridManager == null) return Vector2.zero;
        return new Vector2(gridManager.GridWidth * cellSpacing, gridManager.GridHeight * cellSpacing);
    }
    
    
    
    
    private void Awake()
    {
        if (Instance == null)
        {
            Instance = this;
        }
        else
        {
            Destroy(gameObject);
            return;
        }
        
        InitializeServices();
    }
    
    private void Start()
    {
        LoadAndGenerateLevel();
    }

    private void InitializeServices()
    {
        gridManager = new GridManager();
        
        gridParent = new GameObject("GridParent").transform;
        gridParent.SetParent(transform);
        gridParent.localPosition = Vector3.zero;
    }

    private void Update()
    {
        HandleDebugInput();
        HandleTimer();
    }

    private void HandleTimer()
    {
        if (!isTimerRunning) return;

        remainingTime -= Time.deltaTime;
        
        if (remainingTime <= 0)
        {
            remainingTime = 0;
            isTimerRunning = false;
            isLevelOver = true; // cbj-creative patch
            if (UIManager.Instance != null)
            {
                UIManager.Instance.ShowFail();
            }
        }

        if (UIManager.Instance != null)
        {
            UIManager.Instance.UpdateTimer(remainingTime);
        }
    }

    private void HandleDebugInput()
    {
        if (Input.GetKeyDown(KeyCode.R))
        {
            SceneManager.LoadScene(SceneManager.GetActiveScene().buildIndex);
        }
    }
    private void LoadAndGenerateLevel()
    {
        LevelData levelData = null;
        
        if (useLevelManager && LevelManager.Instance != null)
        {
            levelData = LevelManager.Instance.LoadStartLevel();
        }
        
        if (levelData == null)
        {
            levelData = placeHolderLevelData;
        }
        
        if (levelData != null)
        {
            GenerateBoard(levelData);
        }
        else
        {
        }
    }
    
    public void LoadLevel(int levelNumber)
    {
        if (LevelManager.Instance == null)
        {
            return;
        }
        
        ClearBoard();
        
        LevelData levelData = LevelManager.Instance.LoadLevel(levelNumber);
        if (levelData != null)
        {
            GenerateBoard(levelData);
        }
    }
    public void LoadLevelByName(string levelName)
    {
        if (LevelManager.Instance == null)
        {
            Debug.LogError("[GameManager] LevelManager not found!");
            return;
        }
        
        ClearBoard();
        
        LevelData levelData = LevelManager.Instance.LoadLevelByName(levelName);
        if (levelData != null)
        {
            GenerateBoard(levelData);
        }
    }
    
    public void LoadNextLevel()
    {
        if (LevelManager.Instance == null)
        {
            return;
        }
        
        ClearBoard();
        
        LevelData levelData = LevelManager.Instance.LoadNextLevel();
        if (levelData != null)
        {
            GenerateBoard(levelData);
        }
    }
    
    public void ReloadCurrentLevel()
    {
        if (LevelManager.Instance == null)
        {
            return;
        }
        
        ClearBoard();
        
        LevelData levelData = LevelManager.Instance.ReloadCurrentLevel();
        if (levelData != null)
        {
            GenerateBoard(levelData);
        }
    }

    public void ClearBoard()
    {
        foreach (var block in spawnedBlocks)
        {
            if (block != null)
            {
                Destroy(block);
            }
        }
        spawnedBlocks.Clear();
        
        if (gridParent != null)
        {
            for (int i = gridParent.childCount - 1; i >= 0; i--)
            {
                Destroy(gridParent.GetChild(i).gameObject);
            }
        }
        
        OnBoardCleared?.Invoke();
    }

    private void GenerateBoard(LevelData levelData)
    {
        // Initialize Level UI
        if (UIManager.Instance != null)
        {
            int levelNum = LevelManager.Instance != null ? LevelManager.Instance.CurrentLevelNumber : 1;
            UIManager.Instance.UpdateLevel(levelNum);
            
            remainingTime = levelData.timerCount;
            isTimerRunning = false;
            hasGameStarted = false;
            UIManager.Instance.UpdateTimer(remainingTime);
        }
        leavingBlocks.Clear(); // cbj-creative patch
        isLevelOver = false;

        gridManager.CreateGrid(
            levelData, 
            cellPrefab, 
            gridParent, 
            transform.position, 
            cellSpacing, 
            exitParticlePrefab
        );
        
        DeactivateInactiveCells(levelData);
        
        SpawnBlocks(levelData);
        
        OnBoardGenerated?.Invoke();
        
    }
    
    
    private void DeactivateInactiveCells(LevelData levelData)
    {
        if (levelData.inactiveCells == null || levelData.inactiveCells.Count == 0)
            return;
        
        foreach (var pos in levelData.inactiveCells)
        {
            if (gridManager.IsInBounds(pos.x, pos.y))
            {
                Cell cell = gridManager.GetCell(pos.x, pos.y);
                if (cell != null)
                {
                    cell.gameObject.SetActive(false);
                }
            }
        }
        
    }

    private void SpawnBlocks(LevelData levelData)
    {
        if (levelData.GridBlockDatas == null) return;
        
        foreach (var gridBlockData in levelData.GridBlockDatas)
        {
            Vector2Int pos = gridBlockData.gridPosition;
            if (gridManager.IsInBounds(pos.x, pos.y))
            {
                Cell cell = gridManager.GetCell(pos.x, pos.y);
                
                // Skip inactive cells
                if (!cell.gameObject.activeSelf) continue;
                
                BlockData data = itemFactory.GetBlockData(gridBlockData.blockColor);
                
                if (data != null)
                {
                    BoardItem blockItem = itemFactory.SpawnBlock(cell, data, gridBlockData.shapeOffsets, blockYScaleMultiplier, blockYOffset);
                    if (blockItem != null)
                    {
                        spawnedBlocks.Add(blockItem.gameObject);
                    }
                }
                else
                {
                }
            }
        }
    }
    
    public void StartTimer()
    {
        if (!hasGameStarted && remainingTime > 0)
        {
            isTimerRunning = true;
            hasGameStarted = true;
            OnGameStarted?.Invoke();
        }
    }

    // cbj-creative patch: ExitService.PerformExit calls this when a block starts to slide out.
    // Once every block still on the board is on its way out, the level is solved, so the clock
    // stops here; the win screen still waits for the last slide to end (OnBlockExited).
    public void OnBlockExitStarted(GameObject blockObj)
    {
        if (isLevelOver || !spawnedBlocks.Contains(blockObj) || !leavingBlocks.Add(blockObj)) return;
        if (leavingBlocks.Count >= spawnedBlocks.Count) isTimerRunning = false;
    }

    public void OnBlockExited(GameObject blockObj)
    {
        if (spawnedBlocks.Contains(blockObj))
        {
            spawnedBlocks.Remove(blockObj);
        }
        leavingBlocks.Remove(blockObj); // cbj-creative patch
        if (isLevelOver) return; // the fail screen is already showing: no second ending

        if (spawnedBlocks.Count == 0)
        {
            isLevelOver = true;
            isTimerRunning = false;
            if (UIManager.Instance != null)
            {
                UIManager.Instance.ShowWin();
            }
            OnLevelComplete();
        }
    }

    public void OnLevelComplete()
    {
        if (LevelManager.Instance != null)
        {
            LevelManager.Instance.CompleteCurrentLevel();
        }
    }
}
